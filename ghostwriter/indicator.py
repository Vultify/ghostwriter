"""The listening pill: a small bar at the bottom center of the screen while Ghostwriter listens or types.

It's a layered window that never takes focus and lets clicks pass through, so it can't get in the way of a paste.
"""

import ctypes
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from ctypes import wintypes

import numpy as np
from PIL import Image, ImageDraw

from ghostwriter import win32
from ghostwriter.state import State
from ghostwriter.win32 import gdi32, kernel32, user32

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

# Mic loudness range mapped onto the bars, from room quiet to normal speaking.
QUIET_DB, LOUD_DB = -55.0, -15.0

_CLASS_NAME = "GhostwriterIndicator"
_EX_STYLE = (
    win32.WS_EX_LAYERED | win32.WS_EX_TRANSPARENT | win32.WS_EX_TOPMOST | win32.WS_EX_TOOLWINDOW | win32.WS_EX_NOACTIVATE
)
_window_proc = win32.WNDPROC(lambda window, message, wparam, lparam: user32.DefWindowProcW(window, message, wparam, lparam))
_class_lock = threading.Lock()


def loudness(rms: float) -> float:
    """Map a mic RMS level onto 0 to 1 for the bars."""
    db = 20 * math.log10(max(rms, 1e-9))
    return min(1.0, max(0.0, (db - QUIET_DB) / (LOUD_DB - QUIET_DB)))


class Indicator:
    def __init__(self, level: Callable[[], float]) -> None:
        self.level = level
        self.window: int | None = None
        self._mode: State | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopping = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="Indicator", daemon=True)
        self._thread.start()
        self._ready.wait()

    def show(self, mode: State | None) -> None:
        """Show the pill for LISTENING or WORKING, or fade it out with None."""
        self._mode = mode

    def stop(self) -> None:
        self._stopping.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        scale = user32.GetDpiForSystem() / 96
        size = wintypes.SIZE(round(WIDTH * scale), round(HEIGHT * scale))
        self.window = _create_window(size, scale)
        surface = _Surface(self.window, size)
        self._ready.set()
        try:
            self._animate(surface, scale)
        finally:
            surface.close()
            user32.DestroyWindow(self.window)

    def _animate(self, surface: "_Surface", scale: float) -> None:
        opacity = 0.0
        shown = State.LISTENING
        targets = deque([0.0] * BAR_COUNT, maxlen=BAR_COUNT)
        heights = [0.0] * BAR_COUNT
        next_sample = 0.0
        message = wintypes.MSG()
        while not self._stopping.is_set():
            while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, win32.PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
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
            if shown is State.LISTENING and mode is not None and now >= next_sample:
                targets.append(loudness(self.level()))
                next_sample = now + LEVEL_SAMPLE_SECONDS
            heights = [h + (t - h) * BAR_EASING for h, t in zip(heights, targets)]

            surface.present(_draw(shown, heights, now, (surface.size.cx, surface.size.cy), scale), opacity)
            time.sleep(1 / FPS)


def _create_window(size: wintypes.SIZE, scale: float) -> int:
    instance = kernel32.GetModuleHandleW(None)
    with _class_lock:
        window_class = win32.WNDCLASSEXW(
            cbSize=ctypes.sizeof(win32.WNDCLASSEXW),
            lpfnWndProc=_window_proc,
            hInstance=instance,
            lpszClassName=_CLASS_NAME,
        )
        if not user32.RegisterClassExW(ctypes.byref(window_class)):
            if ctypes.get_last_error() != win32.ERROR_CLASS_ALREADY_EXISTS:
                raise ctypes.WinError(ctypes.get_last_error())
    area = wintypes.RECT()
    user32.SystemParametersInfoW(win32.SPI_GETWORKAREA, 0, ctypes.byref(area), 0)
    x = (area.left + area.right - size.cx) // 2
    y = area.bottom - size.cy - round(BOTTOM_MARGIN * scale)
    window = user32.CreateWindowExW(
        _EX_STYLE, _CLASS_NAME, "Ghostwriter", win32.WS_POPUP, x, y, size.cx, size.cy, None, None, instance, None
    )
    if not window:
        raise ctypes.WinError(ctypes.get_last_error())
    return window


class _Surface:
    """A bitmap the pill is drawn into, pushed to the screen with per pixel transparency."""

    def __init__(self, window: int, size: wintypes.SIZE) -> None:
        self.window = window
        self.size = size
        self.visible = False
        self._screen = user32.GetDC(None)
        self._memory = gdi32.CreateCompatibleDC(self._screen)
        info = win32.BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(win32.BITMAPINFOHEADER)
        info.bmiHeader.biWidth = size.cx
        info.bmiHeader.biHeight = -size.cy  # negative means rows run top to bottom
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = win32.BI_RGB
        self._pixels = ctypes.c_void_p()
        self._bitmap = gdi32.CreateDIBSection(self._memory, ctypes.byref(info), win32.DIB_RGB_COLORS,
                                              ctypes.byref(self._pixels), None, 0)
        self._previous = gdi32.SelectObject(self._memory, self._bitmap)
        rect = wintypes.RECT()
        user32.GetWindowRect(window, ctypes.byref(rect))
        self._position = wintypes.POINT(rect.left, rect.top)

    def present(self, image: Image.Image, opacity: float) -> None:
        rgba = np.asarray(image, dtype=np.uint16)
        alpha = rgba[..., 3:]
        # Windows wants blue, green, red, alpha, with colors already multiplied by alpha.
        premultiplied = (rgba[..., 2::-1] * alpha // 255).astype(np.uint8)
        pixels = np.dstack((premultiplied, alpha.astype(np.uint8))).tobytes()
        ctypes.memmove(self._pixels, pixels, len(pixels))
        blend = win32.BLENDFUNCTION(win32.AC_SRC_OVER, 0, round(255 * opacity), win32.AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(self.window, self._screen, ctypes.byref(self._position), ctypes.byref(self.size),
                                   self._memory, ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend),
                                   win32.ULW_ALPHA)
        if opacity > 0 and not self.visible:
            user32.ShowWindow(self.window, win32.SW_SHOWNOACTIVATE)
            self.visible = True
        elif opacity == 0 and self.visible:
            user32.ShowWindow(self.window, win32.SW_HIDE)
            self.visible = False

    def close(self) -> None:
        gdi32.SelectObject(self._memory, self._previous)
        gdi32.DeleteObject(self._bitmap)
        gdi32.DeleteDC(self._memory)
        user32.ReleaseDC(None, self._screen)


def _draw(mode: State, heights: list[float], now: float, size: tuple[int, int], scale: float) -> Image.Image:
    width, height = size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE
    unit = scale * SUPERSAMPLE  # one logical pixel
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=height / 2, fill=BACKGROUND, outline=BORDER,
                           width=max(1, round(unit)))
    middle = height / 2
    if mode is State.LISTENING:
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
