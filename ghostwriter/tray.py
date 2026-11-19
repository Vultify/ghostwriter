"""The system tray icon: a little ghost by the clock that turns red while listening, with Ghostwriter's settings menu."""

import os
import threading
from collections.abc import Callable
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from ghostwriter.paths import PROJECT
from ghostwriter.settings import HOTKEYS, LOWERED_SOUNDS, Settings
from ghostwriter.state import State
from ghostwriter.system import desktop, hotkey, tray_icon

ICON_SIZE = 64
SUPERSAMPLE = 4
RED = (255, 69, 58, 255)
LIGHT_TASKBAR_COLOR = (32, 32, 32, 255)
DARK_TASKBAR_COLOR = (255, 255, 255, 255)
OFF_OPACITY = 110  # out of 255: a faded ghost while dictation is off
PANEL_SETTINGS = ("dictation", "hotkey", "microphone", "sounds", "pill", "other_sounds", "history")


class Tray:
    """The tray icon and its menu. Menu changes are saved right away and reported through on_change."""

    def __init__(
        self,
        settings: Settings,
        microphones: list[str],
        on_quit: Callable[[], None],
        files: dict[str, Path],
        on_check_updates: Callable[[], None] = lambda: None,
        on_open: Callable[[], None] = lambda: None,
    ) -> None:
        self.settings = settings
        self.on_change: Callable[[], None] = lambda: None
        self._state: State | None = None  # None until startup finishes
        self._microphones = microphones
        color = LIGHT_TASKBAR_COLOR if desktop.taskbar_is_light() else DARK_TASKBAR_COLOR
        normal = draw_ghost(color)
        self._off_icon = draw_ghost(color[:3] + (OFF_OPACITY,))
        listening = draw_ghost(RED)
        self._icons = {State.READY: normal, State.LISTENING: listening, State.LOCKED: listening, State.WORKING: normal}
        menu = pystray.Menu(
            # The default item also runs on a left click of the ghost.
            pystray.MenuItem("Open Ghostwriter", lambda: on_open(), default=True),
            *([self._switch("Dictation", "dictation")] if tray_icon.DICTATION_SWITCH else []),
            pystray.Menu.SEPARATOR,
            # Hidden while the desktop's own dictation keys drive Ghostwriter.
            pystray.MenuItem("Hotkey", pystray.Menu(*(self._choice("hotkey", name) for name in HOTKEYS)),
                             visible=lambda item: hotkey.desktop_keys() is None),
            pystray.MenuItem(
                "Microphone",
                pystray.Menu(
                    self._choice("microphone", None, label=f"{desktop.NAME} default"),
                    *(self._choice("microphone", name) for name in microphones),
                ),
            ),
            self._switch("Sounds", "sounds"),
            self._switch("Listening pill", "pill"),
            # On lowers them to the default; the app window has the other levels.
            pystray.MenuItem("Lower other sounds while listening",
                             lambda: self._change(other_sounds=100 if settings.other_sounds < 100 else LOWERED_SOUNDS),
                             checked=lambda item: settings.other_sounds < 100),
            self._switch("Save history", "history"),
            pystray.Menu.SEPARATOR,
            *(pystray.MenuItem(label, _opener(path)) for label, path in files.items()),
            pystray.MenuItem("Check for updates", lambda: on_check_updates()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Ghostwriter", lambda: on_quit()),
        )
        self._tray = tray_icon.Icon("Ghostwriter", normal, "Ghostwriter: starting up", menu)

    def start(self) -> None:
        shown = threading.Event()

        def show(icon: pystray.Icon) -> None:
            icon.visible = True
            shown.set()

        threading.Thread(target=self._tray.run, args=(show,), name="Tray", daemon=True).start()
        shown.wait(5)
        self._show()

    def notify(self, message: str) -> None:
        """Pop up a notification from the tray icon."""
        self._tray.notify(message, "Ghostwriter")

    def set_state(self, state: State) -> None:
        self._state = state
        self._show()

    def refresh(self) -> None:
        """Show settings changed elsewhere, like in the app window, in the menu's checkmarks and the tooltip."""
        self._tray.update_menu()
        self._show()

    @property
    def dictation_on(self) -> bool:
        """Whether the hotkey dictates. Always, on a system without the Dictation switch."""
        return self.settings.dictation or not tray_icon.DICTATION_SWITCH

    def stop(self) -> None:
        tray_icon.publish(self._status("stopped"))
        self._tray.stop()

    def _show(self) -> None:
        """Show the state and settings on the ghost and its tooltip, and in the bar's panel where there is one."""
        if not self.dictation_on:
            self._tray.icon = self._off_icon
        else:
            self._tray.icon = self._icons[self._state or State.READY]
        keys = hotkey.desktop_keys()
        self._tray.title = self._tooltip(keys)
        tray_icon.publish(self._status(self._state.value if self._state else "starting", keys))

    def _status(self, state: str, keys: dict | None = None) -> dict:
        """What a bar panel needs to show Ghostwriter and change its settings."""
        return {
            "pid": os.getpid(),
            "state": state,
            "project": str(PROJECT),
            "settings": str(self.settings.path),
            "hotkeys": list(HOTKEYS),
            "microphones": list(self._microphones),
            "defaultMicrophone": f"{desktop.NAME} default",
            "loweredSounds": LOWERED_SOUNDS,
            "desktopKeys": keys,  # the desktop's own dictation keys, while they drive Ghostwriter
            # The values in use, so the panel shows the right ones before settings.json exists.
            "values": {name: getattr(self.settings, name) for name in PANEL_SETTINGS},
        }

    def _tooltip(self, keys: dict | None) -> str:
        if keys:
            return self._desktop_keys_tooltip(keys)
        hotkey = self.settings.hotkey
        if self._state is not None and not self.dictation_on:
            return f"Ghostwriter: dictation is off, so {hotkey} works normally"
        return {
            None: "Ghostwriter: starting up",
            State.READY: f"Ghostwriter: hold {hotkey} to talk, double tap for hands free",
            State.LISTENING: "Ghostwriter: listening",
            State.LOCKED: f"Ghostwriter: listening hands free (tap {hotkey} to stop)",
            State.WORKING: "Ghostwriter: typing",
        }[self._state]

    def _desktop_keys_tooltip(self, keys: dict) -> str:
        hold, toggle = keys["hold"], keys["toggle"]
        if self._state is not None and not self.dictation_on:
            return f"Ghostwriter: dictation is off, so {keys['desktop']}'s dictation keys do nothing"
        return {
            None: "Ghostwriter: starting up",
            State.READY: f"Ghostwriter: hold {hold} to talk, or press {toggle} for hands free" if hold
            else f"Ghostwriter: press {toggle} to talk hands free",
            State.LISTENING: "Ghostwriter: listening",
            State.LOCKED: f"Ghostwriter: listening hands free (press {toggle} to stop)",
            State.WORKING: "Ghostwriter: typing",
        }[self._state]

    def _switch(self, label: str, setting: str) -> pystray.MenuItem:
        """A row that turns a setting on and off, with a checkmark while it's on."""
        return pystray.MenuItem(label, lambda: self._change(**{setting: not getattr(self.settings, setting)}),
                                checked=lambda item: getattr(self.settings, setting))

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
        self._show()
        self.on_change()


def _opener(path: Path) -> Callable[[], None]:
    return lambda: desktop.open_path(path)


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
    icon.putalpha(shape.point(lambda level: level * color[3] // 255))  # a see-through color fades the whole ghost
    return icon.resize((final_size, final_size), Image.LANCZOS)

