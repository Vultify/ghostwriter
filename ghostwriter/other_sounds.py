"""Turns other apps' sound down (or off) while Ghostwriter listens, so music and videos don't get in the way, then
back up.

Each app fades to a share of its own volume, picked in Settings, and back again on a thread of its own, so dictation
never waits on it.
The volumes it changed are saved to a file until they're back, so if Ghostwriter stops in the middle, the next
start puts them back.
"""

import json
import logging
import queue
import threading
import time
from collections.abc import Callable
from datetime import date, timedelta
from functools import partial
from pathlib import Path

from ghostwriter.paths import LOWERED_SOUNDS_PATH
from ghostwriter.system import volume

FADE_DOWN_SECONDS = 0.15
FADE_UP_SECONDS = 0.4
STEP_SECONDS = 0.02
CHANGED = 0.02  # a volume further than this from where Ghostwriter left it was changed by hand, so it stays
PENDING_DAYS = 30  # a volume left down by a stop is given up on if its app hasn't shown up in this long
READ_ATTEMPTS, READ_RETRY_SECONDS = 5, 0.2  # for a saved file another program briefly holds open

log = logging.getLogger("ghostwriter")


class OtherSounds:
    def __init__(self, path: Path = LOWERED_SOUNDS_PATH,
                 apps: Callable[..., list[volume.AppVolume]] = volume.other_apps,
                 prepare_thread: Callable[[], None] = volume.prepare_thread) -> None:
        self.path = path
        self._apps = apps
        self._prepare_thread = prepare_thread
        self._lowered: list[tuple[volume.AppVolume, float, float]] = []  # each app, its volume, and what it's at now
        self._pending: dict[str, list] = {}  # left down by an earlier stop: app key -> [its volume, lowered to, date]
        self._commands: queue.Queue[Callable[[], None] | None] = queue.Queue()  # None stops the thread
        self._thread = threading.Thread(target=self._run, name="Other sounds", daemon=True)
        self._thread.start()

    def lower(self, level: float) -> None:
        """Fade other apps to this share of their own volume, from 0 (muted) to 1. Asking again while they're
        already down does nothing."""
        self._commands.put(partial(self._lower, level))

    def restore(self) -> None:
        """Fade them back up to where they were, unless someone changed an app's volume in the meantime."""
        self._commands.put(self._restore)

    def wait(self) -> None:
        """Return once everything asked for so far is done."""
        self._commands.join()

    def close(self) -> None:
        """Put everything back and stop."""
        self._commands.put(None)
        self._thread.join(timeout=5)

    def _run(self) -> None:
        try:
            self._prepare_thread()
        except Exception:
            log.exception("Can't change other apps' volume on this PC, so they'll stay as they are")
            self._apps = lambda playing_only=True: []  # finds no apps, so every request does nothing
        saved = self._read_saved()
        self._pending = saved or {}
        if saved is not None:  # couldn't read the file at all: leave it rather than lose what's in it
            self._handle(self._save)  # drops what's too old to wait for
        self._handle(self._put_back_pending)
        while True:
            command = self._commands.get()
            self._handle(command or self._restore)
            self._commands.task_done()
            if command is None:
                return

    def _handle(self, step: Callable[[], None]) -> None:
        try:
            step()
        except Exception:
            log.exception("Couldn't change other apps' volume")

    def _lower(self, level: float) -> None:
        if self._lowered:
            return
        self._put_back_pending()  # first, so an app a crash left down isn't taken as its real volume
        for app in self._apps():
            try:
                original = app.level
            except OSError:
                continue
            if original > 0:
                self._lowered.append((app, original, original * level))
        if not self._lowered:
            return
        self._save()  # before fading, so even a stop halfway through can be undone
        _fade([(app, original, lowered) for app, original, lowered in self._lowered], FADE_DOWN_SECONDS)

    def _restore(self) -> None:
        if self._lowered:
            fades = []
            for app, original, lowered in self._lowered:
                try:
                    now = app.level
                except OSError:  # the app closed, and Windows will open it at the lowered volume, so put it back then
                    self._pending[app.key] = [original, lowered, date.today().isoformat()]
                    continue
                if abs(now - lowered) <= CHANGED:
                    fades.append((app, now, original))
            self._lowered = []
            _fade(fades, FADE_UP_SECONDS)
            self._save()
        self._put_back_pending()

    def _put_back_pending(self) -> None:
        """Put back volumes an earlier stop left down, for the apps around now, playing or not. Apps that aren't
        open yet are tried again after later dictations."""
        if not self._pending:
            return
        oldest = (date.today() - timedelta(days=PENDING_DAYS)).isoformat()
        found = {key for key, entry in self._pending.items() if entry[2] < oldest}  # given up on
        put_back = 0
        for app in self._apps(playing_only=False):
            if app.key not in self._pending:
                continue
            original, lowered = self._pending[app.key][:2]
            try:
                if abs(app.level - lowered) <= CHANGED:
                    app.level = original
                    put_back += 1
            except OSError:  # listed but already closing; try again next time
                continue
            found.add(app.key)
        for key in found:
            del self._pending[key]
        if found:
            self._save()
        if put_back:
            log.info("Put back the volume of %d app(s) that Ghostwriter had lowered when it stopped", put_back)

    def _read_saved(self) -> dict[str, list] | None:
        """Volumes a stop left down, minus ones too old to still be waiting for. None if the file is there but
        can't be read, like while an antivirus scan holds it."""
        for attempt in range(READ_ATTEMPTS):
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                break
            except FileNotFoundError:
                return {}
            except ValueError:
                log.warning("%s is damaged, so any volumes still lowered stay as they are", self.path.name)
                return {}
            except OSError:
                time.sleep(READ_RETRY_SECONDS)
        else:
            log.warning("Couldn't read %s, so any volumes still lowered stay as they are", self.path.name)
            return None
        if not isinstance(saved, dict):
            return {}
        oldest, today = date.today() - timedelta(days=PENDING_DAYS), date.today().isoformat()
        pending = {}
        for key, entry in saved.items():
            try:
                original, lowered = float(entry[0]), float(entry[1])
                saved_on = entry[2] if len(entry) > 2 else today
                if date.fromisoformat(saved_on) >= oldest:
                    pending[key] = [original, lowered, saved_on]
            except (TypeError, ValueError, IndexError, KeyError):
                log.warning("Skipped a damaged entry in %s", self.path.name)
        return pending

    def _save(self) -> None:
        """Keep the volumes that still need putting back, in case Ghostwriter stops before it gets to them."""
        today = date.today().isoformat()
        saved = {**self._pending, **{app.key: [original, lowered, today] for app, original, lowered in self._lowered}}
        if saved:
            self.path.write_text(json.dumps(saved), encoding="utf-8")
        else:
            self.path.unlink(missing_ok=True)

def _fade(apps: list[tuple[volume.AppVolume, float, float]], seconds: float) -> None:
    """Move each app's volume from its start to its end level in small steps."""
    steps = max(1, round(seconds / STEP_SECONDS))
    for step in range(1, steps + 1):
        for app, start, end in list(apps):
            try:
                app.level = start + (end - start) * step / steps
            except OSError:  # the app closed partway through
                apps.remove((app, start, end))
        if step < steps:
            time.sleep(STEP_SECONDS)
