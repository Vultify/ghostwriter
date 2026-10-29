"""Ghostwriter's settings, changed from the tray menu or the app window and kept in settings.json in the project folder."""

import json
import logging
from dataclasses import dataclass, field
from ctypes import wintypes
from pathlib import Path

from ghostwriter import win32
from ghostwriter.paths import SETTINGS_PATH
from ghostwriter.win32 import user32

# Single keys that make good hotkeys: easy to reach and rarely needed on their own.
HOTKEYS = {
    "Right Alt": win32.VK_RMENU,
    "Right Ctrl": win32.VK_RCONTROL,
    "Caps Lock": win32.VK_CAPITAL,
    "Scroll Lock": win32.VK_SCROLL,
    "Pause": win32.VK_PAUSE,
}
HANDS_FREE_MINUTES = (5, 15, 30)  # how long hands free can run before it stops by itself
THEMES = ("system", "light", "dark")  # for the app window; "system" follows Windows

# Characters that keyboards with an AltGr key (Right Alt on most non-US layouts) type through it.
_ALTGR_CHARACTERS = "@€{}[]\\|~#$^`<>"
_CTRL_AND_ALT = 0x06  # in the shift state VkKeyScanEx reports

log = logging.getLogger("ghostwriter")


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


@dataclass
class Settings:
    hotkey: str = field(default_factory=default_hotkey)
    microphone: str | None = None  # None follows the Windows default mic
    sounds: bool = True
    hands_free: bool = True  # double tap locks recording on
    hands_free_minutes: int = 15
    theme: str = "system"
    history: bool = True  # save each dictation in history.db
    path: Path = field(default=SETTINGS_PATH, repr=False, compare=False)
    _modified: int | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> "Settings":
        """Read the settings file, keeping defaults for anything missing or unreadable."""
        settings = cls(path=path)
        settings._modified = _modified_time(path)
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return settings
        except (OSError, ValueError) as error:
            log.warning("Ignoring unreadable %s: %s", path.name, error)
            return settings
        if not isinstance(saved, dict):
            return settings
        for name, valid in _CHECKS.items():
            if name in saved and valid(saved[name]):
                setattr(settings, name, saved[name])
        return settings

    @property
    def hotkey_code(self) -> int:
        return HOTKEYS[self.hotkey]

    def change(self, name: str, value) -> None:
        """Set one setting and save, refusing values the app can't use."""
        if name not in _CHECKS or not _CHECKS[name](value):
            raise ValueError(f"{value!r} isn't a valid {name}")
        setattr(self, name, value)
        self.save()

    def save(self) -> None:
        values = {name: getattr(self, name) for name in _CHECKS}
        self.path.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
        self._modified = _modified_time(self.path)

    def reload_if_changed(self) -> bool:
        """Pick up changes another program saved, like the app window. Returns whether any setting changed."""
        modified = _modified_time(self.path)
        if modified == self._modified:
            return False
        fresh = Settings.load(self.path)
        self._modified = fresh._modified
        changed = False
        for name in _CHECKS:
            if getattr(fresh, name) != getattr(self, name):
                setattr(self, name, getattr(fresh, name))
                changed = True
        return changed


# What each saved setting may hold; anything else in the file is ignored.
_CHECKS = {
    "hotkey": lambda value: isinstance(value, str) and value in HOTKEYS,
    "microphone": lambda value: value is None or isinstance(value, str),
    "sounds": lambda value: isinstance(value, bool),
    "hands_free": lambda value: isinstance(value, bool),
    "hands_free_minutes": lambda value: value in HANDS_FREE_MINUTES and not isinstance(value, bool),
    "theme": lambda value: value in THEMES,
    "history": lambda value: isinstance(value, bool),
}


def _modified_time(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None
