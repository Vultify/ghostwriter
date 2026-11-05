"""The app window's Windows-only parts: starting it, finding it, bringing it to the front, and its frame. The page is
shown in Microsoft WebView2."""

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

from ghostwriter.paths import PROJECT
from ghostwriter.windows import win32
from ghostwriter.windows.win32 import dwmapi, kernel32, user32

WEB_ENGINE = "edgechromium"  # pywebview's name for WebView2
MISSING_ENGINE_MESSAGE = (
    "Ghostwriter's window needs Microsoft WebView2, which comes with Windows 11 and Microsoft Edge, and it isn't "
    "on this PC.\n\nGet it from https://go.microsoft.com/fwlink/p/?LinkId=2124703\n\n"
    "Dictation still works: use the ghost in the system tray."
)
_FORM_CLASS = "WindowsForms10."  # the window class pywebview's Windows frames use


def open_window() -> None:
    """Start the app window as its own program, with no console."""
    user32.AllowSetForegroundWindow(win32.ASFW_ANY)
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(pythonw if pythonw.exists() else sys.executable), "-m", "ghostwriter.window"], cwd=PROJECT)


def close_window(title: str) -> None:
    for window in _app_windows(title):
        user32.PostMessageW(window, win32.WM_CLOSE, 0, 0)


def bring_to_front(title: str) -> None:
    for window in _app_windows(title):
        user32.ShowWindow(window, win32.SW_RESTORE)
        user32.SetForegroundWindow(window)


def style_frame(window, width: int, height: int) -> None:
    """Round the corners on Windows 11, set the real size, and keep a maximized window off the taskbar."""
    from System import Action  # available once pywebview has loaded .NET
    from System.Drawing import Point, Size
    from System.Windows.Forms import Screen

    form = window.native
    corner = ctypes.c_int(win32.DWMWCP_ROUND)
    dwmapi.DwmSetWindowAttribute(form.Handle.ToInt64(), win32.DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner),
                                 ctypes.sizeof(corner))

    def resize() -> None:
        # Dropping the border shrinks the window by the border's size, so set the size again afterwards.
        area = Screen.FromHandle(form.Handle).WorkingArea
        scale = form.DeviceDpi / 96
        scaled_width, scaled_height = round(width * scale), round(height * scale)
        form.Size = Size(scaled_width, scaled_height)
        form.Location = Point(area.X + (area.Width - scaled_width) // 2, area.Y + (area.Height - scaled_height) // 2)
        form.MaximizedBounds = area

    form.Invoke(Action(resize))  # window changes have to happen on the window's own thread


def _app_windows(title: str) -> list[int]:
    """The app window's handle, found by its title and frame type and by running from this install folder."""
    found = []

    def check(window, _):
        text = ctypes.create_unicode_buffer(64)
        frame = ctypes.create_unicode_buffer(128)
        user32.GetWindowTextW(window, text, len(text))
        user32.GetClassNameW(window, frame, len(frame))
        if text.value == title and frame.value.startswith(_FORM_CLASS) and _runs_from_here(window):
            found.append(window)
        return True

    user32.EnumWindows(win32.WNDENUMPROC(check), 0)
    return found


def _runs_from_here(window: int) -> bool:
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
    if process_id.value == os.getpid():
        return False
    process = kernel32.OpenProcess(win32.PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
    if not process:
        return False
    try:
        name = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(name))
        if not kernel32.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(size)):
            return False
        return name.value.lower().startswith(str(PROJECT).lower())
    finally:
        kernel32.CloseHandle(process)
