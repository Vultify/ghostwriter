"""Ghostwriter's settings, changed from the tray menu or the app window and kept in settings.json in the project folder.

The tray app, the app window, and Omarchy's panel all save to that file, each from its own copy, and none of them
replaces it in one step (the panel's watch on the file would end). So a read can catch another program halfway
through a save, and each save writes only the setting it changes over the file as it is at that moment."""

import json
import logging
import threading
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

# A read that catches a save halfway tries again, 20 ms apart, for up to half a second: a save takes about a
# millisecond, so a file still unreadable after that is broken, and the next save writes it whole again.
_READ_TRIES = 25
HELD = b"\0held by another program"  # what _read_file reports for a file it couldn't open
REPAIR_SECONDS = 10  # how long settings.json stays unreadable, unchanged, before the tray repairs it

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
    _broken: bytes | None = field(default=None, repr=False, compare=False)  # the unreadable file, as last read
    _broken_since: float = field(default=0.0, repr=False, compare=False)  # when it was first seen that way
    _from_file: bool = field(default=False, repr=False, compare=False)  # read from the file at least once
    # The tray menu changes settings on its own thread while the main loop checks the file.
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> "Settings":
        """Read the settings file, keeping defaults for anything missing or unreadable."""
        settings = cls(path=path)
        raw, saved = _read_file(path)
        settings._take(saved or {})
        if saved is None:
            settings._broken, settings._broken_since = raw, time.monotonic()
        else:
            settings._from_file = True
        return settings

    def _take(self, saved: dict) -> None:
        for name, valid in _CHECKS.items():
            if name in saved and valid(saved[name]):
                setattr(self, name, saved[name])

    @property
    def readable(self) -> bool:
        """Whether these settings came from the file, rather than defaults standing in for an unreadable one."""
        return self._broken is None

    @property
    def hotkey_code(self) -> int:
        return HOTKEYS[self.hotkey]

    def change(self, name: str, value) -> bool:
        """Set one setting and save it, refusing values the app can't use. The other settings are written as the
        file has them now, so a change another program saved a moment ago isn't undone, and are taken in here too:
        a caller applies every setting after a change, not only this one. Returns whether it was saved."""
        if name not in _CHECKS or not _CHECKS[name](value):
            raise ValueError(f"{value!r} isn't a valid {name}")
        with self._lock:
            return self._change(name, value)

    def _change(self, name: str, value) -> bool:
        raw, on_disk = _read_file(self.path)
        if on_disk is None and raw is not None:
            # There, but unreadable: saving would write defaults over every other setting. The tray app repairs a
            # file that stays broken (see _reload), so the change waits for that and nothing changes meanwhile.
            log.warning("Didn't save %s, since %s can't be read right now", name, self.path.name)
            return False
        setattr(self, name, value)
        current = Settings(path=self.path)
        current._take(self.saved() if on_disk is None else on_disk)
        merged = {**current.saved(), name: value}
        self._write(merged)
        self._take(merged)  # what another program saved is in use right away, along with this change
        self._from_file = True
        return True

    def saved(self) -> dict:
        """Every saved setting by name, as settings.json holds them."""
        return {name: getattr(self, name) for name in _CHECKS}

    def save(self) -> None:
        self._write(self.saved())

    def _repair(self, broken: bytes) -> None:
        """Write the settings in use over a settings.json that stays unreadable, keeping a copy of the broken one."""
        backup = self.path.with_name(f"{self.path.name}.broken-{time.strftime('%Y%m%d-%H%M%S')}")
        try:
            backup.write_bytes(broken)
            self._write(self.saved())
        except OSError:
            log.warning("Couldn't repair the unreadable %s", self.path.name, exc_info=True)
            return
        log.warning("%s couldn't be read, so it was saved again from the settings in use; the old file is %s",
                    self.path.name, backup.name)

    def _write(self, saved: dict) -> None:
        self.path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
        self._broken = None

    def reload_if_changed(self) -> bool:
        """Pick up changes another program saved, like the app window. Returns whether any setting changed.

        It reads the file every time instead of trusting its modified time: the file is tiny, and on Windows two
        saves in the same clock tick share a modified time, so one of them would go unnoticed."""
        with self._lock:
            return self._reload()

    def _reload(self) -> bool:
        raw, saved = _read_file(self.path, skip=self._broken)
        if saved is None:  # gone or unreadable: keep the settings in use rather than falling back to defaults
            if raw is None or raw == HELD:
                return False  # gone, or held by another program: nothing to repair
            if raw != self._broken:
                self._broken, self._broken_since = raw, time.monotonic()
            elif self._from_file and time.monotonic() - self._broken_since >= REPAIR_SECONDS:
                # The same unreadable file for a while, so not a save still going on or a hand edit being fixed.
                # Only settings once read from the file repair it; defaults standing in would reset everything.
                self._repair(raw)
                self._broken_since = time.monotonic()  # a repair that failed waits as long again
            return False
        self._broken = None
        self._from_file = True
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
    return _read_file(path)[1]


def _read_file(path: Path, skip: bytes | None = None) -> tuple[bytes | None, dict | None]:
    """The file as read and the settings in it, from one read, so what's parsed is what's remembered. The settings
    are None when there's no file (and the file None too) or it can't be read (the file HELD when it couldn't be
    opened); an unreadable file the same as skip isn't waited on again."""
    raw = None
    for attempt in range(_READ_TRIES):
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return None, None
        except OSError as error:  # held by another program, most often one saving it
            raw, problem = HELD, error
        else:
            if raw == skip:
                return raw, None
            try:
                saved = json.loads(raw.decode("utf-8"))
                return raw, saved if isinstance(saved, dict) else None
            except ValueError as error:  # most often a read in the middle of another program's save
                problem = error
        if attempt == _READ_TRIES - 1:
            log.warning("Ignoring unreadable %s: %s", path.name, problem)
            return raw, None
        time.sleep(0.02)
    return raw, None
