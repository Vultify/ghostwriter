"""Small Windows services the rest of Ghostwriter uses: opening files, message boxes, one copy at a time, the light
or dark theme, and playing sounds."""

import ctypes
import os
import winreg
import winsound
from pathlib import Path

from ghostwriter.windows import win32
from ghostwriter.windows.win32 import kernel32, user32

NAME = "Windows"  # for labels like "Windows default" and "Start with Windows"
TITLE = "Ghostwriter"
_PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_SOUND_FLAGS = winsound.SND_FILENAME | winsound.SND_NODEFAULT
_held_names: list[int] = []  # instance mutexes, held until the process exits


def prepare() -> None:
    """Draw crisply on scaled screens. Called once when the tray app starts."""
    user32.SetProcessDpiAwarenessContext(win32.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)


def claim_single_instance(name: str) -> bool:
    """Return False if another program already claimed this name, like a second copy of Ghostwriter."""
    ctypes.set_last_error(0)
    _held_names.append(kernel32.CreateMutexW(None, False, f"Local\\{name}"))
    return ctypes.get_last_error() != win32.ERROR_ALREADY_EXISTS


def open_path(path: Path) -> None:
    """Open a file or folder the way double clicking it would."""
    os.startfile(path)


def show_error(text: str) -> None:
    user32.MessageBoxW(None, text, TITLE, win32.MB_ICONERROR)


def ask_yes_no(question: str) -> bool:
    return user32.MessageBoxW(None, question, TITLE, win32.MB_YESNO | win32.MB_ICONQUESTION) == win32.IDYES


def apps_theme() -> str:
    """Whether Windows is set to light or dark mode for apps."""
    return "light" if _personalize_setting("AppsUseLightTheme") == 1 else "dark"


def taskbar_is_light() -> bool:
    return _personalize_setting("SystemUsesLightTheme") == 1


def play_sound(path: Path, wait: bool = False) -> None:
    """Play a WAV file. Returns right away unless wait is set."""
    winsound.PlaySound(str(path), _SOUND_FLAGS if wait else _SOUND_FLAGS | winsound.SND_ASYNC)


def _personalize_setting(name: str) -> int | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE_KEY) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None
