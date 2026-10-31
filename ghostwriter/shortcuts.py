"""Windows shortcuts that start Ghostwriter with no terminal window: one in the Start menu, made by install.bat, and
one in the Startup folder while "Start with Windows" is on."""

import os
import subprocess
from pathlib import Path

from ghostwriter.paths import ICON_PATH, PROJECT

PYTHONW = PROJECT / ".venv" / "Scripts" / "pythonw.exe"  # pythonw runs without opening a terminal
SHORTCUT_NAME = "Ghostwriter.lnk"
LOGIN_ARGUMENTS = "-m ghostwriter --tray"  # at login, just the ghost in the tray, no window


def start_menu_folder() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def startup_folder() -> Path:
    """Windows starts everything in this folder when you log in."""
    return start_menu_folder() / "Startup"


def make_shortcut(folder: Path, arguments: str = "-m ghostwriter") -> Path:
    path = folder / SHORTCUT_NAME
    script = f"""
$link = (New-Object -ComObject WScript.Shell).CreateShortcut({_quoted(path)})
$link.TargetPath = {_quoted(PYTHONW)}
$link.Arguments = {_quoted(arguments)}
$link.WorkingDirectory = {_quoted(PROJECT)}
$link.IconLocation = {_quoted(ICON_PATH)}
$link.Description = 'Ghostwriter: local dictation'
$link.Save()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    return path


def starts_with_windows(folder: Path | None = None) -> bool:
    return ((folder or startup_folder()) / SHORTCUT_NAME).exists()


def set_start_with_windows(on: bool, folder: Path | None = None) -> None:
    folder = folder or startup_folder()
    if on:
        folder.mkdir(parents=True, exist_ok=True)
        make_shortcut(folder, LOGIN_ARGUMENTS)
    else:
        (folder / SHORTCUT_NAME).unlink(missing_ok=True)


def _quoted(value: object) -> str:
    """Quote a value for PowerShell, so paths with apostrophes (like O'Brien) still work."""
    return "'" + str(value).replace("'", "''") + "'"
