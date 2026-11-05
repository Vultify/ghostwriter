"""The listening pill's window on Windows: a layered window that never takes focus and lets clicks pass through, so
it can't get in the way of a paste. ghostwriter.indicator draws what goes in it."""

import ctypes
import threading
from ctypes import wintypes

import numpy as np
from PIL import Image

from ghostwriter.windows import win32
from ghostwriter.windows.win32 import gdi32, kernel32, user32

_CLASS_NAME = "GhostwriterIndicator"
_EX_STYLE = (
    win32.WS_EX_LAYERED | win32.WS_EX_TRANSPARENT | win32.WS_EX_TOPMOST | win32.WS_EX_TOOLWINDOW | win32.WS_EX_NOACTIVATE
)
_window_proc = win32.WNDPROC(lambda window, message, wparam, lparam: user32.DefWindowProcW(window, message, wparam, lparam))
_class_lock = threading.Lock()


class PillWindow:
    """A window at the bottom center of the screen, sized in logical pixels and scaled for the screen's DPI. Every
    call has to come from the thread that created it."""

    def __init__(self, width: int, height: int, bottom_margin: int) -> None:
        self.scale = user32.GetDpiForSystem() / 96
        self.size = (round(width * self.scale), round(height * self.scale))
        self.handle = _create_window(self.size, round(bottom_margin * self.scale))
        self.visible = False
        self._screen = user32.GetDC(None)
        self._memory = gdi32.CreateCompatibleDC(self._screen)
        info = win32.BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(win32.BITMAPINFOHEADER)
        info.bmiHeader.biWidth = self.size[0]
        info.bmiHeader.biHeight = -self.size[1]  # negative means rows run top to bottom
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = win32.BI_RGB
        self._pixels = ctypes.c_void_p()
        self._bitmap = gdi32.CreateDIBSection(self._memory, ctypes.byref(info), win32.DIB_RGB_COLORS,
                                              ctypes.byref(self._pixels), None, 0)
        self._previous = gdi32.SelectObject(self._memory, self._bitmap)
        rect = wintypes.RECT()
        user32.GetWindowRect(self.handle, ctypes.byref(rect))
        self._position = wintypes.POINT(rect.left, rect.top)
        self._message = wintypes.MSG()

    def pump(self) -> None:
        """Handle the window's waiting messages, which Windows expects of every window's thread."""
        message = ctypes.byref(self._message)
        while user32.PeekMessageW(message, None, 0, 0, win32.PM_REMOVE):
            user32.TranslateMessage(message)
            user32.DispatchMessageW(message)

    def present(self, image: Image.Image, opacity: float) -> None:
        """Show one frame, faded to opacity; at 0 the window hides."""
        rgba = np.asarray(image, dtype=np.uint16)
        alpha = rgba[..., 3:]
        # Windows wants blue, green, red, alpha, with colors already multiplied by alpha.
        premultiplied = (rgba[..., 2::-1] * alpha // 255).astype(np.uint8)
        pixels = np.dstack((premultiplied, alpha.astype(np.uint8))).tobytes()
        ctypes.memmove(self._pixels, pixels, len(pixels))
        blend = win32.BLENDFUNCTION(win32.AC_SRC_OVER, 0, round(255 * opacity), win32.AC_SRC_ALPHA)
        size = wintypes.SIZE(*self.size)
        user32.UpdateLayeredWindow(self.handle, self._screen, ctypes.byref(self._position), ctypes.byref(size),
                                   self._memory, ctypes.byref(wintypes.POINT(0, 0)), 0, ctypes.byref(blend),
                                   win32.ULW_ALPHA)
        if opacity > 0 and not self.visible:
            user32.ShowWindow(self.handle, win32.SW_SHOWNOACTIVATE)
            self.visible = True
        elif opacity == 0 and self.visible:
            user32.ShowWindow(self.handle, win32.SW_HIDE)
            self.visible = False

    def close(self) -> None:
        gdi32.SelectObject(self._memory, self._previous)
        gdi32.DeleteObject(self._bitmap)
        gdi32.DeleteDC(self._memory)
        user32.ReleaseDC(None, self._screen)
        user32.DestroyWindow(self.handle)


def _create_window(size: tuple[int, int], bottom_margin: int) -> int:
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
    x = (area.left + area.right - size[0]) // 2
    y = area.bottom - size[1] - bottom_margin
    window = user32.CreateWindowExW(
        _EX_STYLE, _CLASS_NAME, "Ghostwriter", win32.WS_POPUP, x, y, size[0], size[1], None, None, instance, None
    )
    if not window:
        raise ctypes.WinError(ctypes.get_last_error())
    return window
