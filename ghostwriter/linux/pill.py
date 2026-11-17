"""The listening pill's window on Linux: an overlay layer drawn by its own program (ghostwriter.linux.pill_overlay),
since GTK 4 can't share a process with the GTK 3 parts of Ghostwriter. ghostwriter.indicator draws what goes in it."""

import logging
import queue
import subprocess
import sys
import threading
import time
from contextlib import suppress

import numpy as np
from PIL import Image

from ghostwriter.linux import pill_overlay
from ghostwriter.linux.processes import Children
from ghostwriter.paths import PROJECT

OVERLAY = [sys.executable, "-m", "ghostwriter.linux.pill_overlay"]
RESTART_DELAY = 5.0  # seconds before starting the overlay again after it quit
MAX_RESTARTS = 3

log = logging.getLogger("ghostwriter")


class PillWindow:
    """A pill at the bottom center of the screen in use, sized in logical pixels and scaled for that screen. Every
    call has to come from the thread that created it.

    The overlay starts the first time the pill shows, so with the pill switched off it never runs. Until it's ready,
    frames are dropped rather than queued."""

    def __init__(self, width: int, height: int, bottom_margin: int) -> None:
        self._logical = (width, height)
        self._margin = bottom_margin
        self.scale = 1.0
        self.size = (width, height)
        self.visible = False
        self._children = Children()
        self._overlay: subprocess.Popen | None = None
        self._listener: threading.Thread | None = None
        self._ready = threading.Event()
        self._scales: queue.SimpleQueue[float] = queue.SimpleQueue()  # from the overlay, applied on this thread
        self._never = False  # the desktop or the system can't show it, so it's never started again
        self._restarts = 0
        self._restart_at = 0.0

    def pump(self) -> None:
        """Take up a new screen scale between frames, so size and scale always change together."""
        scale = None
        while not self._scales.empty():
            scale = self._scales.get()
        if scale is not None and scale != self.scale:
            self.scale = scale
            self.size = (round(self._logical[0] * scale), round(self._logical[1] * scale))

    def present(self, image: Image.Image, opacity: float) -> None:
        """Show one frame, faded to opacity; at 0 the pill hides."""
        visible = opacity > 0
        if not (visible or self.visible) or not self._running():
            return
        rgba = np.asarray(image, dtype=np.uint16)
        alpha = rgba[..., 3:] * round(255 * opacity) // 255
        # Cairo wants blue, green, red, alpha, with colors already multiplied by alpha.
        pixels = np.dstack((rgba[..., 2::-1] * alpha // 255, alpha)).astype(np.uint8)
        try:
            self._overlay.stdin.write(pill_overlay.FRAME_HEADER.pack(image.width, image.height, visible))
            self._overlay.stdin.write(pixels.tobytes())
            self._overlay.stdin.flush()
        except (BrokenPipeError, ValueError):
            self._lost()
            return
        self.visible = visible

    def close(self) -> None:
        if self._overlay is not None:
            with suppress(OSError):
                self._overlay.stdin.close()  # the overlay quits when its frames end
            with suppress(subprocess.TimeoutExpired):
                self._overlay.wait(timeout=2)
        self._children.close()  # ends one that's stuck
        if self._overlay is not None:
            with suppress(subprocess.TimeoutExpired):
                self._overlay.wait(timeout=2)
            self._overlay = None

    def _running(self) -> bool:
        """Whether the overlay takes frames, starting it if it isn't running."""
        if self._overlay is not None and self._overlay.poll() is not None:
            self._lost()
        if self._overlay is None:
            if self._never or time.monotonic() < self._restart_at:
                return False
            self._start()
        return self._ready.is_set()

    def _start(self) -> None:
        width, height = self._logical
        self._ready = threading.Event()
        self._overlay = self._children.start([*OVERLAY, str(width), str(height), str(self._margin)], cwd=PROJECT,
                                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self._listener = threading.Thread(target=self._listen, args=(self._overlay.stdout, self._ready),
                                          name="Pill overlay", daemon=True)
        self._listener.start()

    def _lost(self) -> None:
        with suppress(OSError):
            self._overlay.stdin.close()
        with suppress(subprocess.TimeoutExpired):
            self._overlay.wait(timeout=1)
        self._listener.join(timeout=1)  # its last words may say why it quit
        if not self._never:
            self._restarts += 1
            if self._restarts > MAX_RESTARTS:
                self._never = True
                log.warning("The listening pill's overlay keeps quitting, so the pill is off until Ghostwriter "
                            "restarts")
            else:
                log.warning("The listening pill's overlay quit, so it starts again on the next dictation")
        self._overlay = None
        self.visible = False
        self._restart_at = time.monotonic() + RESTART_DELAY

    def _listen(self, replies, ready: threading.Event) -> None:
        for line in replies:
            word, _, rest = line.decode().strip().partition(" ")
            if word == pill_overlay.READY:
                ready.set()
            elif word == "scale":
                self._scales.put(float(rest))
            elif word == pill_overlay.UNSUPPORTED:
                self._never = True
                log.info("This desktop has no overlay layers, so the listening pill doesn't show")
            elif word == pill_overlay.MISSING:
                self._never = True
                log.warning("The listening pill needs gtk4-layer-shell and GTK 4, so it doesn't show (%s)", rest)
