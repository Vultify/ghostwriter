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
from functools import partial
from pathlib import Path

from ghostwriter.paths import LOWERED_SOUNDS_PATH
from ghostwriter.system import volume

FADE_DOWN_SECONDS = 0.15
FADE_UP_SECONDS = 0.4
STEP_SECONDS = 0.02
CHANGED = 0.02  # a volume further than this from where Ghostwriter left it was changed by hand, so it stays

log = logging.getLogger("ghostwriter")


class OtherSounds:
    def __init__(self, path: Path = LOWERED_SOUNDS_PATH,
                 apps: Callable[[], list[volume.AppVolume]] = volume.other_apps,
                 prepare_thread: Callable[[], None] = volume.prepare_thread) -> None:
        self.path = path
        self._apps = apps
        self._prepare_thread = prepare_thread
        self._lowered: list[tuple[volume.AppVolume, float, float]] = []  # each app, its volume, and what it's at now
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
            self._apps = list  # finds no apps, so every request does nothing
        self._handle(self._put_back_after_a_stop)
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
        for app in self._apps():
            try:
                original = app.level
            except OSError:
                continue
            if original > 0:
                self._lowered.append((app, original, original * level))
        if not self._lowered:
            return
        # Saved before fading, so even a stop halfway through can be undone.
        self.path.write_text(json.dumps({app.key: [original, lowered] for app, original, lowered in self._lowered}),
                             encoding="utf-8")
        _fade([(app, original, lowered) for app, original, lowered in self._lowered], FADE_DOWN_SECONDS)

    def _restore(self) -> None:
        if not self._lowered:
            return
        fades = []
        for app, original, lowered in self._lowered:
            try:
                now = app.level
            except OSError:  # the app closed
                continue
            if abs(now - lowered) <= CHANGED:
                fades.append((app, now, original))
        self._lowered = []
        _fade(fades, FADE_UP_SECONDS)
        self.path.unlink(missing_ok=True)

    def _put_back_after_a_stop(self) -> None:
        """Ghostwriter stopped while other apps were down: put back the ones still running."""
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            saved = {}
        put_back = 0
        for app in self._apps():
            try:
                if app.key in saved and abs(app.level - saved[app.key][1]) <= CHANGED:
                    app.level = saved[app.key][0]
                    put_back += 1
            except OSError:
                continue
        self.path.unlink(missing_ok=True)
        if put_back:
            log.info("Put back the volume of %d app(s) that Ghostwriter had lowered when it stopped", put_back)


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
