"""The listening pill: a small bar at the bottom center of the screen while Ghostwriter listens or types.

This draws it and animates it; ghostwriter.system supplies the window it shows in, which never takes focus and lets
clicks pass through, so it can't get in the way of a paste.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from PIL import Image, ImageDraw

from ghostwriter.audio import loudness
from ghostwriter.state import State
from ghostwriter.system import pill

# Sizes are in logical pixels and get scaled for the screen's DPI.
WIDTH, HEIGHT = 104, 32
BOTTOM_MARGIN = 56
BAR_COUNT = 11
FPS = 60
FADE_STEP = 0.2
BAR_EASING = 0.35
LEVEL_SAMPLE_SECONDS = 0.05
SUPERSAMPLE = 3  # draw large and shrink, for smooth edges

BACKGROUND = (24, 24, 27, 235)
BORDER = (255, 255, 255, 38)
RED = (255, 69, 58, 255)
WHITE = (255, 255, 255, 235)


class Indicator:
    def __init__(self, level: Callable[[], float]) -> None:
        self.level = level
        self.window: pill.PillWindow | None = None
        self._mode: State | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopping = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="Indicator", daemon=True)
        self._thread.start()
        self._ready.wait()

    def show(self, mode: State | None) -> None:
        """Show the pill for LISTENING, LOCKED, or WORKING, or fade it out with None."""
        self._mode = mode

    def stop(self) -> None:
        self._stopping.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        self.window = pill.PillWindow(WIDTH, HEIGHT, BOTTOM_MARGIN)  # made on this thread, which then drives it
        self._ready.set()
        try:
            self._animate(self.window)
        finally:
            self.window.close()

    def _animate(self, window: "pill.PillWindow") -> None:
        opacity = 0.0
        shown = State.LISTENING
        targets = deque([0.0] * BAR_COUNT, maxlen=BAR_COUNT)
        heights = [0.0] * BAR_COUNT
        next_sample = 0.0
        while not self._stopping.is_set():
            window.pump()
            mode = self._mode
            if mode is None and opacity == 0:
                time.sleep(0.03)
                continue
            if mode is not None:
                if opacity == 0:
                    targets.extend([0.0] * BAR_COUNT)
                    heights = [0.0] * BAR_COUNT
                shown = mode
            opacity = min(1.0, opacity + FADE_STEP) if mode else max(0.0, opacity - FADE_STEP)

            now = time.perf_counter()
            if shown.is_recording and mode is not None and now >= next_sample:
                targets.append(loudness(self.level()))
                next_sample = now + LEVEL_SAMPLE_SECONDS
            heights = [h + (t - h) * BAR_EASING for h, t in zip(heights, targets)]

            window.present(_draw(shown, heights, now, window.size, window.scale), opacity)
            time.sleep(1 / FPS)


def _draw(mode: State, heights: list[float], now: float, size: tuple[int, int], scale: float) -> Image.Image:
    width, height = size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE
    unit = scale * SUPERSAMPLE  # one logical pixel
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=height / 2, fill=BACKGROUND, outline=BORDER,
                           width=max(1, round(unit)))
    middle = height / 2
    if mode.is_recording:
        if mode is State.LOCKED:
            # A stop square instead of the dot: recording is hands free and a tap stops it.
            half = 4 * unit
            draw.rounded_rectangle((16 * unit - half, middle - half, 16 * unit + half, middle + half),
                                   radius=1.5 * unit, fill=RED)
        else:
            _dot(draw, 16 * unit, middle, 4.5 * unit, RED)
        left, right = 30 * unit, (WIDTH - 16) * unit
        step = (right - left) / (BAR_COUNT - 1)
        bar = 3 * unit
        for index, level in enumerate(heights):
            x = left + index * step
            half = (2 + level * 9) * unit
            draw.rounded_rectangle((x - bar / 2, middle - half, x + bar / 2, middle + half), radius=bar / 2, fill=WHITE)
    else:
        # Three dots that brighten one after another while the text is being typed.
        for index in range(3):
            phase = (now * 2.2 - index * 0.18) % 1
            alpha = round(90 + 165 * math.sin(phase * math.pi))
            _dot(draw, width / 2 + (index - 1) * 11 * unit, middle, 3 * unit, (255, 255, 255, alpha))
    return image.resize(size, Image.LANCZOS)


def _dot(draw: ImageDraw.ImageDraw, x: float, y: float, radius: float, color: tuple[int, int, int, int]) -> None:
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
