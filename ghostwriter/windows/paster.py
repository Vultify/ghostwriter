"""Pasting on Windows: put the text on the clipboard, press Ctrl+V in whatever app has focus, then put the old
clipboard back. Also says which app is in front, for History."""

import ctypes
import functools
import io
import time
from ctypes import wintypes
from pathlib import Path

from ghostwriter.paths import PROJECT
from ghostwriter.windows import win32
from ghostwriter.windows.clipboard import Clipboard
from ghostwriter.windows.processes import program_path
from ghostwriter.windows.win32 import gdi32, shell32, user32, version

# Long enough for slow apps (browsers, terminals) to read the clipboard before we restore it.
RESTORE_DELAY_SECONDS = 0.5

App = Path  # the app in front, known on Windows by its program file

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
        try:
            _wait_for_modifiers_released()
            _send_ctrl_v()
            time.sleep(self.restore_delay)
        finally:
            restored = self.clipboard.restore(previous, sequence)  # even if Windows blocked the paste
        return restored


def foreground_app() -> App | None:
    """The program file of the window in front, or None if Windows won't say."""
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(process_id))
    return program_path(process_id.value)


@functools.lru_cache(maxsize=64)
def app_name(program: App | None) -> str:
    """A program's everyday name, like "Google Chrome" for chrome.exe, taken from its file details."""
    if program is None:
        return "Unknown app"
    if program.is_relative_to(PROJECT):
        return "Ghostwriter"  # the app window's own Python
    details = _file_details(program)
    # Store apps keep their real name in the product name; other programs in the description.
    keys = ("ProductName", "FileDescription") if "WindowsApps" in program.parts else ("FileDescription", "ProductName")
    return next((details[key] for key in keys if details.get(key)), program.stem)


def app_icon(program: App | None, size: int = 48) -> bytes | None:
    """A program's own icon as a PNG, for History, or None when it has none."""
    if program is None:
        return None
    icon = wintypes.HICON()
    if shell32.SHDefExtractIconW(str(program), 0, 0, ctypes.byref(icon), None, size) != 0 or not icon:
        return None
    try:
        on_black, on_white = _draw_icon(icon, size, 0x00), _draw_icon(icon, size, 0xFF)
    finally:
        user32.DestroyIcon(icon)
    if on_black is None or on_white is None:
        return None

    import numpy as np  # only loaded when a new app needs its icon
    from PIL import Image

    # Drawn over black and over white, a pixel shows how opaque it is by how little the background shows through.
    # That works the same for icons with soft edges and for old icons with only a mask, and keeps their black parts.
    black = np.frombuffer(on_black, np.uint8).reshape(size, size, 4)[..., :3].astype(np.float32)
    white = np.frombuffer(on_white, np.uint8).reshape(size, size, 4)[..., :3].astype(np.float32)
    alpha = np.clip(255 - (white - black).max(axis=2), 0, 255)
    color = np.where(alpha[..., None] > 0, black * 255 / np.maximum(alpha[..., None], 1), 0)
    rgba = np.dstack([np.clip(color, 0, 255)[..., ::-1], alpha]).round().astype(np.uint8)  # BGR to RGB
    png = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(png, "PNG")
    return png.getvalue()


def _draw_icon(icon: wintypes.HICON, size: int, background: int) -> bytes | None:
    """The icon drawn over a solid gray level, as top-down BGRA pixels."""
    header = win32.BITMAPINFOHEADER(biSize=ctypes.sizeof(win32.BITMAPINFOHEADER), biWidth=size, biHeight=-size,
                                    biPlanes=1, biBitCount=32)
    bits = ctypes.c_void_p()
    canvas = gdi32.CreateCompatibleDC(None)
    bitmap = gdi32.CreateDIBSection(canvas, ctypes.byref(win32.BITMAPINFO(bmiHeader=header)), 0,
                                    ctypes.byref(bits), None, 0)
    try:
        if not bitmap:
            return None
        ctypes.memset(bits, background, size * size * 4)
        previous = gdi32.SelectObject(canvas, bitmap)
        drawn = user32.DrawIconEx(canvas, 0, 0, icon, size, size, 0, None, win32.DI_NORMAL)
        pixels = ctypes.string_at(bits, size * size * 4)
        gdi32.SelectObject(canvas, previous)
        return pixels if drawn else None
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(canvas)


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
