"""Paste text into whatever app has focus, then put the old clipboard back."""

import ctypes
import time
from ctypes import wintypes
from pathlib import Path

from ghostwriter import win32
from ghostwriter.clipboard import Clipboard
from ghostwriter.win32 import kernel32, user32

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


def foreground_app() -> str:
    """The program name of the window in front, for the log."""
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(process_id))
    process = kernel32.OpenProcess(win32.PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
    if not process:
        return f"process {process_id.value}"
    try:
        name = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(name))
        if kernel32.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(size)):
            return Path(name.value).name
        return f"process {process_id.value}"
    finally:
        kernel32.CloseHandle(process)


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
