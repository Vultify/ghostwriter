"""Pasting on Linux: put the text on the clipboard, press the paste keys in whatever app has focus, then put the old
clipboard back. Hyprland presses the keys, so they work in every app, including older X11 ones like games. Also says
which app is in front, for History."""

import functools
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from ghostwriter.linux import desktop_files, hotkey, hyprland
from ghostwriter.linux.clipboard import Clipboard, ClipboardError
from ghostwriter.paths import PROJECT

log = logging.getLogger(__name__)

# Long enough for slow apps (browsers, terminals) to read the clipboard before we restore it.
RESTORE_DELAY_SECONDS = 0.5

_MODIFIERS = (29, 97, 42, 54, 56, 100, 125, 126)  # left and right Ctrl, Shift, Alt, and Super
_MODIFIER_WAIT_SECONDS = 1.0

# Terminals paste with Ctrl+Shift+V, since Ctrl+V means something else in them. Omarchy tags its terminals, and these
# cover the common ones elsewhere.
_TERMINAL_TAG = "terminal"
_TERMINALS = {
    "Alacritty", "kitty", "com.mitchellh.ghostty", "foot", "footclient", "org.codeberg.dnkl.foot",
    "org.wezfurlong.wezterm", "org.gnome.Console", "org.gnome.Terminal", "org.kde.konsole", "xterm", "URxvt",
}

# Chromium-based browsers name a web app's window after its address, like "chrome-web.whatsapp.com__-Default".
_WEB_APP = re.compile(r"^[^.]*?-(?P<address>[^_]+?)__")
_STEAM_GAME = "steam_app_"  # Steam games only give their store number, so their window title names them


class PasteError(RuntimeError):
    pass


class Paster:
    def __init__(self, restore_delay: float = RESTORE_DELAY_SECONDS) -> None:
        self.clipboard = Clipboard()
        self.restore_delay = restore_delay

    def paste(self, text: str) -> bool:
        """Paste text and return whether the old clipboard was put back."""
        if not hyprland.running():
            raise PasteError("Pasting on Linux needs Hyprland for now")
        try:
            previous = self.clipboard.snapshot()
            readable = True
        except ClipboardError:
            log.warning("Couldn't read the clipboard, so it won't be put back after pasting", exc_info=True)
            previous, readable = None, False
        written = self.clipboard.write_text(text)
        _wait_for_modifiers_released()
        hyprland.press_keys(*paste_keys(hyprland.active_window()))
        time.sleep(self.restore_delay)
        return readable and self.clipboard.restore(previous, written)


@dataclass(frozen=True)
class App:
    """The app in front: its program file, plus the app id and title its window has."""

    program: Path | None
    app_id: str
    title: str

    @property
    def name(self) -> str:
        """A short name for the log."""
        return self.app_id or (self.program.name if self.program else "an unknown app")


def foreground_app() -> App | None:
    """The app in front, or None when there's no window or the desktop won't say."""
    if not hyprland.running():
        return None
    try:
        window = hyprland.active_window()
    except (OSError, ValueError, hyprland.HyprlandError):
        return None
    if not window:
        return None
    return App(_program(window.get("pid", -1)), window.get("class") or window.get("initialClass", ""),
               window.get("title", ""))


@functools.lru_cache(maxsize=64)
def app_name(app: App | None) -> str:
    """An app's everyday name, like "WhatsApp" for its web app window, taken from its launcher entry."""
    if app is None:
        return "Unknown app"
    if app.program and app.program.is_relative_to(PROJECT):
        return "Ghostwriter"  # the app window's own Python
    if entry := desktop_files.find(app.app_id):
        return entry.name
    if web_app := _WEB_APP.match(app.app_id):
        address = web_app["address"]
        return entry.name if (entry := desktop_files.opening(address)) else address
    if app.app_id.startswith(_STEAM_GAME) and app.title:
        return app.title
    return app.app_id or (app.program.stem if app.program else "Unknown app")


def paste_keys(window: dict) -> tuple[str, str]:
    """The modifiers and key that paste in a window: Ctrl+Shift+V in terminals, Ctrl+V everywhere else."""
    tags = {tag.rstrip("*") for tag in window.get("tags", [])}
    terminal = _TERMINAL_TAG in tags or window.get("class") in _TERMINALS
    return ("CTRL SHIFT" if terminal else "CTRL"), "V"


def _program(pid: int) -> Path | None:
    try:
        return Path(os.readlink(f"/proc/{pid}/exe"))
    except OSError:
        return None


def _wait_for_modifiers_released() -> None:
    """A held Shift, Ctrl, Alt, or Super would mix into our paste keys and make a different shortcut."""
    deadline = time.perf_counter() + _MODIFIER_WAIT_SECONDS
    while time.perf_counter() < deadline and hotkey.keys_down(_MODIFIERS):
        time.sleep(0.01)
