"""The listening pill's window on Linux: an overlay layer drawn by its own program (ghostwriter.linux.pill_overlay),
since GTK 4 can't share a process with the GTK 3 parts of Ghostwriter. ghostwriter.indicator draws what goes in it."""

import logging
import subprocess
import sys
import threading

import numpy as np
from PIL import Image

from ghostwriter.linux import pill_overlay
from ghostwriter.linux.processes import Children
from ghostwriter.paths import PROJECT

log = logging.getLogger("ghostwriter")


class PillWindow:
    """A pill at the bottom center of the screen in use, sized in logical pixels and scaled for that screen. Every
    call has to come from the thread that created it."""

    def __init__(self, width: int, height: int, bottom_margin: int) -> None:
        self._logical = (width, height)
        self.scale = 1.0
        self.size = (width, height)
        self.visible = False
        self._unsupported = False
        self._children = Children()
        self._overlay: subprocess.Popen | None = self._children.start(
            [sys.executable, "-m", "ghostwriter.linux.pill_overlay", str(width), str(height), str(bottom_margin)],
            cwd=PROJECT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        threading.Thread(target=self._listen, args=(self._overlay.stdout,), name="Pill scale", daemon=True).start()

    def pump(self) -> None:
        pass

    def present(self, image: Image.Image, opacity: float) -> None:
        """Show one frame, faded to opacity; at 0 the pill hides."""
        if self._overlay is None or self._unsupported:
            return
        visible = opacity > 0
        if not visible and not self.visible:
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
            log.warning("The listening pill's overlay closed, so the pill is off until Ghostwriter restarts")
            self._overlay = None
            return
        self.visible = visible

    def close(self) -> None:
        if self._overlay is not None:
            try:
                self._overlay.stdin.close()  # the overlay quits when its frames end
            except BrokenPipeError:
                pass
            try:
                self._overlay.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._overlay.terminate()
            self._overlay = None
        self._children.close()

    def _listen(self, replies) -> None:
        for line in replies:
            words = line.decode().split()
            if words == [pill_overlay.UNSUPPORTED]:
                self._unsupported = True
                log.info("This desktop has no overlay layers, so the listening pill doesn't show")
            elif len(words) == 2 and words[0] == "scale":
                self.scale = float(words[1])
                self.size = (round(self._logical[0] * self.scale), round(self._logical[1] * self.scale))
