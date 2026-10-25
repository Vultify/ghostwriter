"""The system tray icon: a little ghost by the clock that turns red while listening, with Ghostwriter's settings menu."""

import os
import threading
import winreg
from collections.abc import Callable
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from ghostwriter.settings import HOTKEYS, Settings
from ghostwriter.state import State

ICON_SIZE = 64
SUPERSAMPLE = 4
RED = (255, 69, 58, 255)
LIGHT_TASKBAR_COLOR = (32, 32, 32, 255)
DARK_TASKBAR_COLOR = (255, 255, 255, 255)


class Tray:
    """The tray icon and its menu. Menu changes are saved right away and reported through on_change."""

    def __init__(
        self,
        settings: Settings,
        microphones: list[str],
        on_quit: Callable[[], None],
        files: dict[str, Path],
    ) -> None:
        self.settings = settings
        self.on_change: Callable[[], None] = lambda: None
        self._state: State | None = None  # None until startup finishes
        normal = draw_ghost(LIGHT_TASKBAR_COLOR if _taskbar_is_light() else DARK_TASKBAR_COLOR)
        listening = draw_ghost(RED)
        self._icons = {State.READY: normal, State.LISTENING: listening, State.LOCKED: listening, State.WORKING: normal}
        menu = pystray.Menu(
            pystray.MenuItem("Hotkey", pystray.Menu(*(self._choice("hotkey", name) for name in HOTKEYS))),
            pystray.MenuItem(
                "Microphone",
                pystray.Menu(
                    self._choice("microphone", None, label="Windows default"),
                    *(self._choice("microphone", name) for name in microphones),
                ),
            ),
            pystray.MenuItem("Sounds", lambda: self._change(sounds=not settings.sounds),
                             checked=lambda item: settings.sounds),
            pystray.Menu.SEPARATOR,
            *(pystray.MenuItem(label, _opener(path)) for label, path in files.items()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Ghostwriter", lambda: on_quit()),
        )
        self._tray = pystray.Icon("Ghostwriter", normal, "Ghostwriter: starting up", menu)

    def start(self) -> None:
        shown = threading.Event()

        def show(icon: pystray.Icon) -> None:
            icon.visible = True
            shown.set()

        threading.Thread(target=self._tray.run, args=(show,), name="Tray", daemon=True).start()
        shown.wait(5)

    def notify(self, message: str) -> None:
        """Pop up a Windows notification from the tray icon."""
        self._tray.notify(message, "Ghostwriter")

    def set_state(self, state: State) -> None:
        self._state = state
        self._tray.icon = self._icons[state]
        self._tray.title = self._tooltip()

    def stop(self) -> None:
        self._tray.stop()

    def _tooltip(self) -> str:
        hotkey = self.settings.hotkey
        return {
            None: "Ghostwriter: starting up",
            State.READY: f"Ghostwriter: hold {hotkey} to talk, double tap for hands free",
            State.LISTENING: "Ghostwriter: listening",
            State.LOCKED: f"Ghostwriter: listening hands free (tap {hotkey} to stop)",
            State.WORKING: "Ghostwriter: typing",
        }[self._state]

    def _choice(self, setting: str, value: str | None, label: str | None = None) -> pystray.MenuItem:
        return pystray.MenuItem(
            label or value,
            lambda: self._change(**{setting: value}),
            checked=lambda item: getattr(self.settings, setting) == value,
            radio=True,
        )

    def _change(self, **changes) -> None:
        for name, value in changes.items():
            setattr(self.settings, name, value)
        self.settings.save()
        self._tray.update_menu()
        self._tray.title = self._tooltip()
        self.on_change()


def _opener(path: Path) -> Callable[[], None]:
    return lambda: os.startfile(path)


def draw_ghost(color: tuple[int, int, int, int], final_size: int = ICON_SIZE) -> Image.Image:
    """A ghost silhouette with cut out eyes, drawn large and shrunk for smooth edges."""
    size = final_size * SUPERSAMPLE
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
    return icon.resize((final_size, final_size), Image.LANCZOS)


def _taskbar_is_light() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "SystemUsesLightTheme")[0] == 1
    except OSError:
        return False
