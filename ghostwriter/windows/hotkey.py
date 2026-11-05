"""The hotkey on Windows: the keys to pick from, and a system wide hook for one key that reports presses and hides
the key from every other app."""

import ctypes
import threading
from collections.abc import Callable
from ctypes import wintypes

from ghostwriter.windows import win32
from ghostwriter.windows.win32 import kernel32, user32

# Single keys that make good hotkeys: easy to reach and rarely needed on their own.
HOTKEYS = {
    "Right Alt": win32.VK_RMENU,
    "Right Ctrl": win32.VK_RCONTROL,
    "Caps Lock": win32.VK_CAPITAL,
    "Scroll Lock": win32.VK_SCROLL,
    "Pause": win32.VK_PAUSE,
}

# Characters that keyboards with an AltGr key (Right Alt on most non-US layouts) type through it.
_ALTGR_CHARACTERS = "@€{}[]\\|~#$^`<>"
_CTRL_AND_ALT = 0x06  # in the shift state VkKeyScanEx reports
_KEY_DOWN_MESSAGES = (win32.WM_KEYDOWN, win32.WM_SYSKEYDOWN)


def keyboard_uses_altgr() -> bool:
    """Whether any installed keyboard layout types characters with AltGr, which would make Right Alt a bad hotkey."""
    count = user32.GetKeyboardLayoutList(0, None)
    layouts = (wintypes.HKL * count)()
    user32.GetKeyboardLayoutList(count, layouts)
    for layout in layouts:
        for character in _ALTGR_CHARACTERS:
            key = user32.VkKeyScanExW(character, layout)
            if key != -1 and (key >> 8) & _CTRL_AND_ALT == _CTRL_AND_ALT:
                return True
    return False


def default_hotkey() -> str:
    return "Right Ctrl" if keyboard_uses_altgr() else "Right Alt"


class KeyHook:
    """Calls on_press and on_release for one key and swallows it, so the app in front never sees it.

    The callbacks run on the hook thread and must return right away, or Windows drops the hook.
    """

    def __init__(
        self,
        vk_code: int,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        allow_injected: bool = False,
    ) -> None:
        self.vk_code = vk_code
        self.on_press = on_press
        self.on_release = on_release
        self.allow_injected = allow_injected
        self._held = False
        self._proc = win32.HOOKPROC(self._handle)  # kept on self so ctypes doesn't free it
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._error: OSError | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="KeyHook", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._error:
            raise self._error

    def set_key(self, vk_code: int) -> None:
        """Switch to a different key without reinstalling the hook."""
        self._held = False
        self.vk_code = vk_code

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            user32.PostThreadMessageW(self._thread_id, win32.WM_QUIT, 0, 0)
            self._thread.join(timeout=2)

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, win32.PM_NOREMOVE)  # creates the message queue
        hook = user32.SetWindowsHookExW(win32.WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            self._error = ctypes.WinError(ctypes.get_last_error())
            self._ready.set()
            return
        self._ready.set()
        try:
            # Windows calls the hook from inside this loop, so it has to keep running.
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                pass
        finally:
            user32.UnhookWindowsHookEx(hook)

    def _handle(self, code: int, message: int, data: int) -> int:
        if code == win32.HC_ACTION:
            key = win32.KBDLLHOOKSTRUCT.from_address(data)
            injected = key.flags & win32.LLKHF_INJECTED
            if key.vkCode == self.vk_code and (self.allow_injected or not injected):
                is_down = message in _KEY_DOWN_MESSAGES
                if is_down and not self._held:
                    self._held = True
                    self.on_press()
                elif not is_down and self._held:
                    self._held = False
                    self.on_release()
                return 1
        return user32.CallNextHookEx(None, code, message, data)
