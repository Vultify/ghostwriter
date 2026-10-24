"""The system tray icon: a little ghost by the clock that turns red while Ghostwriter is listening."""

import threading
import winreg
from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

from ghostwriter.state import State

ICON_SIZE = 64
SUPERSAMPLE = 4
RED = (255, 69, 58, 255)
LIGHT_TASKBAR_COLOR = (32, 32, 32, 255)
DARK_TASKBAR_COLOR = (255, 255, 255, 255)

TOOLTIPS = {
    State.READY: "Ghostwriter: hold Right Alt to talk",
    State.LISTENING: "Ghostwriter: listening",
    State.WORKING: "Ghostwriter: typing",
}


class Tray:
    def __init__(self, on_quit: Callable[[], None]) -> None:
        normal = draw_ghost(LIGHT_TASKBAR_COLOR if _taskbar_is_light() else DARK_TASKBAR_COLOR)
        self._icons = {State.READY: normal, State.LISTENING: draw_ghost(RED), State.WORKING: normal}
        menu = pystray.Menu(pystray.MenuItem("Quit Ghostwriter", lambda: on_quit()))
        self._tray = pystray.Icon("Ghostwriter", self._icons[State.READY], TOOLTIPS[State.READY], menu)

    def start(self) -> None:
        threading.Thread(target=self._tray.run, name="Tray", daemon=True).start()

    def set_state(self, state: State) -> None:
        self._tray.icon = self._icons[state]
        self._tray.title = TOOLTIPS[state]

    def stop(self) -> None:
        self._tray.stop()


def draw_ghost(color: tuple[int, int, int, int]) -> Image.Image:
    """A ghost silhouette with cut out eyes, drawn large and shrunk for smooth edges."""
    size = ICON_SIZE * SUPERSAMPLE
    shape = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(shape)
    left, right, top, hem = 0.16 * size, 0.84 * size, 0.08 * size, 0.80 * size
    width = right - left
    draw.ellipse((left, top, right, top + width), fill=255)
    draw.rectangle((left, top + width / 2, right, hem), fill=255)
    bump = width / 6
    for index in range(3):
        x = left + bump * (1 + 2 * index)
        draw.ellipse((x - bump, hem - bump, x + bump, hem + bump), fill=255)
    eye_width, eye_height, eye_y = 0.09 * size, 0.14 * size, top + width * 0.42
    for x in (0.40 * size, 0.60 * size):
        draw.ellipse((x - eye_width / 2, eye_y - eye_height / 2, x + eye_width / 2, eye_y + eye_height / 2), fill=0)
    icon = Image.new("RGBA", (size, size), color)
    icon.putalpha(shape)
    return icon.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)


def _taskbar_is_light() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "SystemUsesLightTheme")[0] == 1
    except OSError:
        return False
