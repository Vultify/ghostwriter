"""Ghostwriter's settings, changed from the tray menu or the app window and kept in settings.json in the project folder."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ghostwriter.models import ENGINE_SETTINGS
from ghostwriter.paths import SETTINGS_PATH
from ghostwriter.sounds import STYLES
from ghostwriter.system import hotkey as system_hotkey

HOTKEYS = system_hotkey.HOTKEYS  # the keys to pick from, by name; the names are the same on every system
HANDS_FREE_MINUTES = (5, 15, 30)  # how long hands free can run before it stops by itself
THEMES = ("system", "light", "dark")  # for the app window; "system" follows the system's own setting

log = logging.getLogger("ghostwriter")


@dataclass
class Settings:
    hotkey: str = field(default_factory=system_hotkey.default_hotkey)
    microphone: str | None = None  # None follows the system's default mic
    sounds: bool = True
    sound: str = "soft"  # which start and stop sounds, from sounds.STYLES
    pill: bool = True  # the listening pill at the bottom of the screen
    hands_free: bool = True  # double tap locks recording on
    hands_free_minutes: int = 15
    theme: str = "system"
    history: bool = True  # save each dictation in history.db
    engine: str = "auto"  # speech engine, from models.ENGINE_SETTINGS
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
    "sound": lambda value: value in STYLES,
    "pill": lambda value: isinstance(value, bool),
    "hands_free": lambda value: isinstance(value, bool),
    "hands_free_minutes": lambda value: value in HANDS_FREE_MINUTES and not isinstance(value, bool),
    "theme": lambda value: value in THEMES,
    "history": lambda value: isinstance(value, bool),
    "engine": lambda value: value in ENGINE_SETTINGS,
}


def _modified_time(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None
