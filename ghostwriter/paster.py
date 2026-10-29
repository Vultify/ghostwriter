"""Paste text into whatever app has focus, then put the old clipboard back."""

import ctypes
import functools
import time
from ctypes import wintypes
from pathlib import Path

from ghostwriter import win32
from ghostwriter.clipboard import Clipboard
from ghostwriter.paths import PROJECT
from ghostwriter.win32 import kernel32, user32, version

# Long enough for slow apps (browsers, terminals) to read the clipboard before we restore it.
RESTORE_DELAY_SECONDS = 0.5

_MODIFIERS = (win32.VK_SHIFT, win32.VK_CONTROL, win32.VK_MENU, win32.VK_LWIN, win32.VK_RWIN)
_MODIFIER_WAIT_SECONDS = 1.0


class PasteError(RuntimeError):
    pass


class Paster:
    def __init__(self, restore_delay: float = RESTORE_DELAY_SECONDS) -> None:
        self.clipboard = Clipboard()
        self.restore_delay = restore_delay

    def paste(self, text: str) -> bool:
        """Paste text with Ctrl+V and return whether the old clipboard was put back."""
        previous = self.clipboard.snapshot()
        sequence = self.clipboard.write_text(text)
        _wait_for_modifiers_released()
        _send_ctrl_v()
        time.sleep(self.restore_delay)
        return self.clipboard.restore(previous, sequence)


def foreground_app() -> Path | None:
    """The program file of the window in front, or None if Windows won't say."""
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(process_id))
    process = kernel32.OpenProcess(win32.PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
    if not process:
        return None
    try:
        name = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(name))
        if kernel32.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(size)):
            return Path(name.value)
        return None
    finally:
        kernel32.CloseHandle(process)


@functools.lru_cache(maxsize=64)
def app_name(program: Path | None) -> str:
    """A program's everyday name, like "Google Chrome" for chrome.exe, taken from its file details."""
    if program is None:
        return "Unknown app"
    if program.is_relative_to(PROJECT):
        return "Ghostwriter"  # the app window's own Python
    details = _file_details(program)
    # Store apps keep their real name in the product name; other programs in the description.
    keys = ("ProductName", "FileDescription") if "WindowsApps" in program.parts else ("FileDescription", "ProductName")
    return next((details[key] for key in keys if details.get(key)), program.stem)


def _file_details(program: Path) -> dict[str, str]:
    """The description and product name from a program's version info, when it has them."""
    size = version.GetFileVersionInfoSizeW(str(program), None)
    data = ctypes.create_string_buffer(size) if size else None
    if not data or not version.GetFileVersionInfoW(str(program), 0, size, data):
        return {}
    value, length = wintypes.LPVOID(), wintypes.UINT()
    if not version.VerQueryValueW(data, r"\VarFileInfo\Translation", ctypes.byref(value), ctypes.byref(length)):
        return {}
    language, codepage = ctypes.cast(value, ctypes.POINTER(wintypes.WORD * 2)).contents
    details = {}
    for key in ("FileDescription", "ProductName"):
        path = f"\\StringFileInfo\\{language:04x}{codepage:04x}\\{key}"
        if version.VerQueryValueW(data, path, ctypes.byref(value), ctypes.byref(length)) and length.value:
            details[key] = ctypes.wstring_at(value.value).strip()
    return details


def _wait_for_modifiers_released() -> None:
    """A held Shift, Ctrl, Alt, or Win would turn our Ctrl+V into a different shortcut."""
    deadline = time.perf_counter() + _MODIFIER_WAIT_SECONDS
    while time.perf_counter() < deadline and any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in _MODIFIERS):
        time.sleep(0.01)


def _key_event(vk: int, release: bool = False) -> win32.INPUT:
    event = win32.INPUT(type=win32.INPUT_KEYBOARD)
    event.ki.wVk = vk
    event.ki.wScan = user32.MapVirtualKeyW(vk, win32.MAPVK_VK_TO_VSC)
    event.ki.dwFlags = win32.KEYEVENTF_KEYUP if release else 0
    return event


def _send_ctrl_v() -> None:
    # Sent as one batch so a key the user presses can't land in the middle of it.
    events = (win32.INPUT * 4)(
        _key_event(win32.VK_CONTROL),
        _key_event(win32.VK_V),
        _key_event(win32.VK_V, release=True),
        _key_event(win32.VK_CONTROL, release=True),
    )
    if user32.SendInput(len(events), events, ctypes.sizeof(win32.INPUT)) != len(events):
        raise PasteError(f"Windows blocked the Ctrl+V keystrokes (error {ctypes.get_last_error()})")
