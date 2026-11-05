"""The hotkey on Linux: the keys to pick from, and a reader that watches every keyboard for one key's presses and
releases.

Ghostwriter reads the keyboards directly (/dev/input), so it works on any desktop, but only for users in the input
group. Unlike on Windows the key isn't hidden from other apps; none of these keys does anything on its own in most apps.
"""

import ctypes
import fcntl
import json
import os
import select
import struct
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

# Single keys that make good hotkeys, by their Linux key codes.
HOTKEYS = {
    "Right Alt": 100,
    "Right Ctrl": 97,
    "Caps Lock": 58,
    "Scroll Lock": 70,
    "Pause": 119,
}

NO_ACCESS_MESSAGE = (
    "Ghostwriter can't read the keyboard, so the hotkey won't work.\n\n"
    "Add yourself to the input group, then log out and back in:\n\n"
    "sudo usermod -aG input $USER"
)

_DEVICES = Path("/dev/input")
_SYSFS = Path("/sys/class/input")
_PROGRAM_KEYBOARDS = "/devices/virtual/input/"  # where keyboards made by programs (uinput) live in sysfs
_EVENT = struct.Struct("@llHHi")  # struct input_event: time, type, code, value
_EV_SYN, _EV_KEY = 0, 1
_SYN_DROPPED = 3
_RELEASED, _PRESSED = 0, 1  # 2 means the key is repeating while held
_KEY_STATE_SIZE = 96  # bytes in the kernel's map of which keys are down
_EVIOCGKEY = (2 << 30) | (_KEY_STATE_SIZE << 16) | (ord("E") << 8) | 0x18
_RESCAN_SECONDS = 2.0  # how often to look for keyboards plugged in or paired since the last look

_RIGHT_ALT_XKB = HOTKEYS["Right Alt"] + 8  # xkb numbers keys 8 higher than Linux does
_ISO_LEVEL3_SHIFT = 0xFE03  # the key symbol for AltGr


class _RuleNames(ctypes.Structure):
    _fields_ = [(name, ctypes.c_char_p) for name in ("rules", "model", "layout", "variant", "options")]


def keyboard_uses_altgr() -> bool:
    """Whether the keyboard layout turns Right Alt into AltGr, which types characters and makes it a bad hotkey."""
    try:
        xkb = ctypes.CDLL("libxkbcommon.so.0")
    except OSError:
        return False
    xkb.xkb_context_new.restype = ctypes.c_void_p
    xkb.xkb_context_unref.argtypes = [ctypes.c_void_p]
    xkb.xkb_keymap_new_from_names.restype = ctypes.c_void_p
    xkb.xkb_keymap_new_from_names.argtypes = [ctypes.c_void_p, ctypes.POINTER(_RuleNames), ctypes.c_int]
    xkb.xkb_keymap_unref.argtypes = [ctypes.c_void_p]
    xkb.xkb_keymap_num_layouts.argtypes = [ctypes.c_void_p]
    xkb.xkb_keymap_key_get_syms_by_level.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_uint32)),
    ]

    layout, variant, options = (value.encode() or None for value in _keyboard_layout())
    context = xkb.xkb_context_new(0)
    keymap = xkb.xkb_keymap_new_from_names(context, ctypes.byref(_RuleNames(None, None, layout, variant, options)), 0)
    try:
        for index in range(xkb.xkb_keymap_num_layouts(keymap) if keymap else 0):
            symbols = ctypes.POINTER(ctypes.c_uint32)()
            count = xkb.xkb_keymap_key_get_syms_by_level(keymap, _RIGHT_ALT_XKB, index, 0, ctypes.byref(symbols))
            if count and symbols[0] == _ISO_LEVEL3_SHIFT:
                return True
        return False
    finally:
        if keymap:
            xkb.xkb_keymap_unref(keymap)
        xkb.xkb_context_unref(context)


def default_hotkey() -> str:
    return "Right Ctrl" if keyboard_uses_altgr() else "Right Alt"


class KeyHook:
    """Calls on_press and on_release for one key, read straight from every keyboard. Keyboards plugged in or paired
    later join within a couple of seconds.

    The callbacks run on the reader thread and must return right away. allow_injected also listens to keyboards that
    programs make (uinput); without it, only real keyboards count, like on Windows.
    """

    def __init__(
        self,
        key_code: int,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        allow_injected: bool = False,
    ) -> None:
        self.key_code = key_code
        self.on_press = on_press
        self.on_release = on_release
        self.allow_injected = allow_injected
        self._held_by: int | None = None  # the keyboard holding the key down
        self._keyboards: dict[int, str] = {}  # open file -> device path
        self._refused = False
        self._wake_read = self._wake_write = -1  # a pipe that wakes the reader so it can stop
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._open_new_keyboards()
        if not self._keyboards and self._refused:
            raise PermissionError(NO_ACCESS_MESSAGE)
        self._wake_read, self._wake_write = os.pipe()
        self._thread = threading.Thread(target=self._run, name="KeyHook", daemon=True)
        self._thread.start()

    def set_key(self, key_code: int) -> None:
        """Switch to a different key."""
        self._held_by = None
        self.key_code = key_code

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            os.write(self._wake_write, b"\0")
            self._thread.join(timeout=2)

    def _run(self) -> None:
        next_scan = time.monotonic() + _RESCAN_SECONDS
        try:
            while True:
                ready, _, _ = select.select([self._wake_read, *self._keyboards], [], [], _RESCAN_SECONDS)
                if self._wake_read in ready:
                    return
                for keyboard in ready:
                    self._read(keyboard)
                if time.monotonic() >= next_scan:
                    self._open_new_keyboards()
                    next_scan = time.monotonic() + _RESCAN_SECONDS
        finally:
            for keyboard in self._keyboards:
                os.close(keyboard)
            self._keyboards.clear()
            self._held_by = None
            os.close(self._wake_read)
            os.close(self._wake_write)

    def _read(self, keyboard: int) -> None:
        try:
            data = os.read(keyboard, _EVENT.size * 64)
        except OSError:  # unplugged
            data = b""
        if not data:
            self._forget(keyboard)
            return
        for _, _, kind, code, value in _EVENT.iter_unpack(data[: len(data) - len(data) % _EVENT.size]):
            if kind == _EV_KEY and code == self.key_code:
                self._key(keyboard, value)
            elif kind == _EV_SYN and code == _SYN_DROPPED:
                self._catch_up(keyboard)

    def _key(self, keyboard: int, value: int) -> None:
        if value == _PRESSED and self._held_by is None:
            self._held_by = keyboard
            self.on_press()
        elif value == _RELEASED and self._held_by is not None:
            self._held_by = None
            self.on_release()

    def _catch_up(self, keyboard: int) -> None:
        # The kernel dropped events because the reader fell behind, so ask it whether the key is down right now.
        state = bytearray(_KEY_STATE_SIZE)
        try:
            fcntl.ioctl(keyboard, _EVIOCGKEY, state)
        except OSError:
            return
        down = state[self.key_code // 8] >> (self.key_code % 8) & 1
        self._key(keyboard, _PRESSED if down else _RELEASED)

    def _open_new_keyboards(self) -> None:
        watched = set(self._keyboards.values())
        for path in _keyboards(self.allow_injected):
            if path in watched:
                continue
            try:
                self._keyboards[os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)] = path
            except PermissionError:
                self._refused = True
            except OSError:
                pass

    def _forget(self, keyboard: int) -> None:
        del self._keyboards[keyboard]
        os.close(keyboard)
        if self._held_by == keyboard:  # a keyboard unplugged mid hold lets go of the key
            self._key(keyboard, _RELEASED)


def _keyboards(include_injected: bool) -> list[str]:
    """Device paths for every keyboard that has at least one of the hotkeys."""
    found = []
    for device in sorted(_SYSFS.glob("event*")):
        try:
            keys = _bitmap((device / "device" / "capabilities" / "key").read_text())
            injected = _PROGRAM_KEYBOARDS in str(device.resolve())
        except OSError:
            continue
        if any(keys >> code & 1 for code in HOTKEYS.values()) and (include_injected or not injected):
            found.append(str(_DEVICES / device.name))
    return found


def _bitmap(text: str) -> int:
    """A sysfs capability map: hex words, highest first, each as wide as a C long."""
    width = ctypes.sizeof(ctypes.c_long) * 2
    return int("".join(word.zfill(width) for word in text.split()) or "0", 16)


def _keyboard_layout() -> tuple[str, str, str]:
    """The keyboard layout, variant, and options the desktop uses, or empty ones for xkb's defaults."""
    names = ("layout", "variant", "options")
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        try:
            return tuple(_hyprland_option(f"input:kb_{name}") for name in names)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    try:
        status = subprocess.run(["localectl", "status"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return "", "", ""
    fields = dict(line.strip().split(": ", 1) for line in status.splitlines() if ": " in line)
    return tuple(fields.get(f"X11 {name.capitalize()}", "") for name in names)


def _hyprland_option(name: str) -> str:
    result = subprocess.run(["hyprctl", "-j", "getoption", name], capture_output=True, text=True, timeout=5,
                            check=True)
    return json.loads(result.stdout).get("str", "")
