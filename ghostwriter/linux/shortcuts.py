"""Ghostwriter's launcher entry, so it shows up in the desktop's app launcher with its icon, and a copy of it in the
autostart folder while "Start at login" is on. Both are standard XDG desktop entries: Omarchy's launcher, GNOME, and
KDE all read the same applications folder, and they all start what's in the autostart folder at login.

Run `python -m ghostwriter.linux.shortcuts` from the project folder to add the launcher entry, or to refresh both
entries after the folder moved."""

import os
from pathlib import Path

from ghostwriter.paths import ICON_PATH, PROJECT

APP_ID = "io.github.vultify.Ghostwriter"  # also the window's app id, so desktops match the window to its entry
ENTRY_NAME = f"{APP_ID}.desktop"
PYTHON = PROJECT / ".venv" / "bin" / "python"
LOGIN_ARGUMENTS = ["--tray"]  # at login, just the ghost in the bar, no window
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

_ENTRY = """[Desktop Entry]
Type=Application
Name=Ghostwriter
GenericName=Dictation
Comment=Hold a key, talk, and the text lands where you're typing
Exec={exec}
Path={path}
Icon={icon}
Terminal=false
StartupNotify=false
Categories=Utility;Accessibility;
Keywords=dictation;speech;voice;talk;transcribe;whisper;
"""


def applications_folder() -> Path:
    return _data_home() / "applications"


def icons_folder() -> Path:
    return _data_home() / "icons" / "hicolor"


def autostart_folder() -> Path:
    """Desktops start every entry in this folder when you log in."""
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart"


def make_launcher_entry(folder: Path | None = None, icons: Path | None = None) -> Path:
    """Add Ghostwriter to the app launcher, with its icon at every size launchers and bars ask for."""
    _save_icons(icons or icons_folder())
    return _write_entry((folder or applications_folder()) / ENTRY_NAME, [])


def starts_at_login(folder: Path | None = None) -> bool:
    return ((folder or autostart_folder()) / ENTRY_NAME).exists()


def set_start_at_login(on: bool, folder: Path | None = None) -> None:
    path = (folder or autostart_folder()) / ENTRY_NAME
    if on:
        _write_entry(path, LOGIN_ARGUMENTS)
    else:
        path.unlink(missing_ok=True)


def _write_entry(path: Path, arguments: list[str]) -> Path:
    command = [str(PYTHON), "-m", "ghostwriter", *arguments]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_ENTRY.format(exec=_escape(" ".join(_exec_argument(part) for part in command)),
                                  path=_escape(str(PROJECT)), icon=APP_ID), encoding="utf-8")
    return path


def _save_icons(folder: Path) -> None:
    from PIL import Image

    with Image.open(ICON_PATH) as icon:
        for size in ICON_SIZES:
            target = folder / f"{size}x{size}" / "apps" / f"{APP_ID}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            icon.ico.getimage((size, size)).save(target)  # the .ico carries a drawing at each size


def _exec_argument(argument: str) -> str:
    """Quote one argument of an Exec line, so a project folder with spaces or quotes in its path still starts."""
    if argument and not any(character in argument for character in " \t\n\"'\\><~|&;$*?#()`="):
        return argument
    return '"' + "".join("\\" + character if character in '"`$\\' else character for character in argument) + '"'


def _escape(value: str) -> str:
    """Escape a value the way desktop entry files store strings."""
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


if __name__ == "__main__":
    print(f"Added Ghostwriter to the app launcher: {make_launcher_entry()}")
    if starts_at_login():
        set_start_at_login(True)
        print(f"Refreshed start at login: {autostart_folder() / ENTRY_NAME}")
