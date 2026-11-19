"""Ghostwriter's settings, changed from the tray menu or the app window and kept in settings.json in the project folder.

The tray app, the app window, and Omarchy's panel all save to that file, each from its own copy, and none of them
replaces it in one step (the panel's watch on the file would end). So a read can catch another program halfway
through a save, and each save writes only the setting it changes over the file as it is at that moment."""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from ghostwriter.models import ENGINE_SETTINGS
from ghostwriter.paths import SETTINGS_PATH
from ghostwriter.sounds import STYLES
from ghostwriter.system import hotkey as system_hotkey

HOTKEYS = system_hotkey.HOTKEYS  # the keys to pick from, by name; the names are the same on every system
HANDS_FREE_MINUTES = (5, 15, 30)  # how long hands free can run before it stops by itself
# How loud other apps play while Ghostwriter listens, in percent of their own volume: 100 leaves them be, 0 mutes.
OTHER_SOUNDS = (100, 50, 30, 10, 0)
LOWERED_SOUNDS = 10  # the default, and what the tray's on/off switch turns them down to
THEMES = ("system", "light", "dark")  # for the app window; "system" follows the system's own setting

_READ_TRIES = 5  # a read that catches a save halfway tries again this many times, 20 ms apart

log = logging.getLogger("ghostwriter")


@dataclass
class Settings:
    dictation: bool = True  # off pauses the hotkey, so the key works normally until it's turned back on
    hotkey: str = field(default_factory=system_hotkey.default_hotkey)
    microphone: str | None = None  # None follows the system's default mic
    sounds: bool = True
    sound: str = "soft"  # which start and stop sounds, from sounds.STYLES
    pill: bool = True  # the listening pill at the bottom of the screen
    other_sounds: int = LOWERED_SOUNDS  # how loud other apps play while listening, from OTHER_SOUNDS
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
        settings._take(_read(path) or {})
        return settings

    def _take(self, saved: dict) -> None:
        for name, valid in _CHECKS.items():
            if name in saved and valid(saved[name]):
                setattr(self, name, saved[name])

    @property
    def hotkey_code(self) -> int:
        return HOTKEYS[self.hotkey]

    def change(self, name: str, value) -> None:
        """Set one setting and save it, refusing values the app can't use. The other settings are written as the
        file has them now, so a change another program saved a moment ago isn't undone."""
        if name not in _CHECKS or not _CHECKS[name](value):
            raise ValueError(f"{value!r} isn't a valid {name}")
        setattr(self, name, value)
        on_disk = _read(self.path)
        current = Settings(path=self.path)
        current._take(self.saved() if on_disk is None else on_disk)
        merged = {**current.saved(), name: value}
        self._write(merged)
        if merged == self.saved():  # nothing new in the file, so reload_if_changed has nothing to pick up
            self._modified = _modified_time(self.path)

    def saved(self) -> dict:
        """Every saved setting by name, as settings.json holds them."""
        return {name: getattr(self, name) for name in _CHECKS}

    def save(self) -> None:
        self._write(self.saved())
        self._modified = _modified_time(self.path)

    def _write(self, saved: dict) -> None:
        self.path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")

    def reload_if_changed(self) -> bool:
        """Pick up changes another program saved, like the app window. Returns whether any setting changed."""
        modified = _modified_time(self.path)
        if modified == self._modified:
            return False
        self._modified = modified  # taken before reading, so a save still going on shows up as news next time
        saved = _read(self.path)
        if saved is None:  # gone or unreadable: keep the settings in use rather than falling back to defaults
            return False
        fresh = Settings(path=self.path)
        fresh._take(saved)
        changed = False
        for name in _CHECKS:
            if getattr(fresh, name) != getattr(self, name):
                setattr(self, name, getattr(fresh, name))
                changed = True
        return changed


# What each saved setting may hold; anything else in the file is ignored.
_CHECKS = {
    "dictation": lambda value: isinstance(value, bool),
    "hotkey": lambda value: isinstance(value, str) and value in HOTKEYS,
    "microphone": lambda value: value is None or isinstance(value, str),
    "sounds": lambda value: isinstance(value, bool),
    "sound": lambda value: value in STYLES,
    "pill": lambda value: isinstance(value, bool),
    "other_sounds": lambda value: value in OTHER_SOUNDS and not isinstance(value, bool),
    "hands_free": lambda value: isinstance(value, bool),
    "hands_free_minutes": lambda value: value in HANDS_FREE_MINUTES and not isinstance(value, bool),
    "theme": lambda value: value in THEMES,
    "history": lambda value: isinstance(value, bool),
    "engine": lambda value: value in ENGINE_SETTINGS,
}


def _read(path: Path) -> dict | None:
    """The saved settings, or None when there's no file or it can't be read."""
    for attempt in range(_READ_TRIES):
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:  # most often a read in the middle of another program's save
            if attempt == _READ_TRIES - 1:
                log.warning("Ignoring unreadable %s: %s", path.name, error)
                return None
            time.sleep(0.02)
            continue
        return saved if isinstance(saved, dict) else None
    return None


def _modified_time(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None
