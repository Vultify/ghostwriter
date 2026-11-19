"""Finding an app's icon in the desktop's icon theme, the way launchers do (the freedesktop icon theme spec): the
current theme first, then the themes it inherits from, then hicolor, where most apps install theirs."""

import configparser
import functools
import os
from dataclasses import dataclass
from pathlib import Path

from ghostwriter.linux.desktop_files import data_home

EXTENSIONS = (".png", ".svg", ".xpm")
FALLBACK_THEME = "hicolor"


@dataclass(frozen=True)
class _Folder:
    path: str  # relative to the theme, like "48x48/apps"
    size: int
    scalable: bool
    min_size: int
    max_size: int


def find(name: str, size: int) -> Path | None:
    """The file for an icon name (or a path to one) that best fits a size, or None when no theme has it."""
    if not name:
        return None
    if os.path.isabs(name):
        return Path(name) if os.path.isfile(name) else None
    stem = name[: -len(Path(name).suffix)] if Path(name).suffix in EXTENSIONS else name  # some entries add one
    for theme in _themes():
        if found := _in_theme(theme, stem, size):
            return found
    for folder in _base_folders():  # icons that aren't in any theme
        for extension in EXTENSIONS:
            if f"{stem}{extension}" in _files(folder.parent / "pixmaps"):
                return folder.parent / "pixmaps" / f"{stem}{extension}"
    return None


def current_theme() -> str:
    """The icon theme the desktop uses: GNOME's setting (which Omarchy sets too), else GTK's settings file."""
    from gi.repository import Gio

    schema = "org.gnome.desktop.interface"
    if Gio.SettingsSchemaSource.get_default().lookup(schema, True):
        if theme := Gio.Settings.new(schema).get_string("icon-theme"):
            return theme
    settings = configparser.ConfigParser()
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    settings.read(config / "gtk-3.0" / "settings.ini")
    return settings.get("Settings", "gtk-icon-theme-name", fallback=FALLBACK_THEME)


@functools.cache
def _themes() -> tuple[str, ...]:
    """The current theme and everything it inherits from, in order, ending with hicolor."""
    order, waiting = [], [current_theme()]
    while waiting:
        theme = waiting.pop(0)
        if theme in order or not _index(theme):
            continue
        order.append(theme)
        waiting += [parent.strip() for parent in _index(theme).get("Inherits", "").split(",") if parent.strip()]
    if FALLBACK_THEME not in order:
        order.append(FALLBACK_THEME)
    return tuple(order)


def _in_theme(theme: str, name: str, size: int) -> Path | None:
    best, best_distance = None, None
    for folder in _folders(theme):
        for base in _base_folders():
            directory = base / theme / folder.path
            for extension in EXTENSIONS:
                if f"{name}{extension}" not in _files(directory):
                    continue
                distance = _distance(folder, size)
                if best_distance is None or distance < best_distance:
                    best, best_distance = directory / f"{name}{extension}", distance
                if distance == 0:
                    return best
    return best


@functools.cache
def _files(directory: Path) -> frozenset[str]:
    """The file names in an icon folder, read once, since a lookup checks hundreds of folders."""
    try:
        return frozenset(os.listdir(directory))
    except OSError:
        return frozenset()


def _distance(folder: _Folder, size: int) -> int:
    """How far a folder's icons are from the size wanted. Any icon at least that big wins over a smaller one,
    since shrinking stays sharp and growing blurs."""
    if folder.scalable and folder.min_size <= size <= folder.max_size:
        return 0
    if folder.size >= size:
        return folder.size - size
    return 100_000 + size - folder.size


@functools.cache
def _folders(theme: str) -> tuple[_Folder, ...]:
    index = _index(theme)
    if not index:
        return ()
    names = [name.strip() for key in ("Directories", "ScaledDirectories")
             for name in index.get(key, "").split(",") if name.strip()]
    folders = []
    for name in dict.fromkeys(names):
        section = _section(theme, name)
        if section.get("Scale", "1") != "1":  # high-DPI copies of the same icons
            continue
        size = int(section.get("Size", "0") or 0)
        scalable = section.get("Type", "Threshold") == "Scalable"
        folders.append(_Folder(name, size, scalable, int(section.get("MinSize", size) or size),
                               int(section.get("MaxSize", size) or size)))
    return tuple(folders)


@functools.cache
def _parsed(theme: str) -> configparser.ConfigParser | None:
    for base in _base_folders():
        index = base / theme / "index.theme"
        if index.is_file():
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.optionxform = str  # keys are case sensitive
            try:
                parser.read(index, encoding="utf-8")
            except (configparser.Error, UnicodeError):
                return None
            return parser
    return None


def _index(theme: str) -> dict:
    parser = _parsed(theme)
    return dict(parser["Icon Theme"]) if parser and parser.has_section("Icon Theme") else {}


def _section(theme: str, name: str) -> dict:
    parser = _parsed(theme)
    return dict(parser[name]) if parser and parser.has_section(name) else {}


def _base_folders() -> list[Path]:
    shared = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [Path.home() / ".icons", data_home() / "icons",
            *(Path(folder) / "icons" for folder in shared.split(":") if folder)]


def clear_cache() -> None:
    """Forget what was read, for when the theme or its files change (and for tests)."""
    _themes.cache_clear()
    _folders.cache_clear()
    _parsed.cache_clear()
    _files.cache_clear()
