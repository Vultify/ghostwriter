"""Pasting on Linux: put the text on the clipboard, press the paste keys in whatever app has focus, then put the old
clipboard back. Hyprland presses the keys, so they work in every app, including older X11 ones like games."""

import logging
import time

from ghostwriter.linux import hotkey, hyprland
from ghostwriter.linux.clipboard import Clipboard, ClipboardError

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


def paste_keys(window: dict) -> tuple[str, str]:
    """The modifiers and key that paste in a window: Ctrl+Shift+V in terminals, Ctrl+V everywhere else."""
    tags = {tag.rstrip("*") for tag in window.get("tags", [])}
    terminal = _TERMINAL_TAG in tags or window.get("class") in _TERMINALS
    return ("CTRL SHIFT" if terminal else "CTRL"), "V"


def _wait_for_modifiers_released() -> None:
    """A held Shift, Ctrl, Alt, or Super would mix into our paste keys and make a different shortcut."""
    deadline = time.perf_counter() + _MODIFIER_WAIT_SECONDS
    while time.perf_counter() < deadline and hotkey.keys_down(_MODIFIERS):
        time.sleep(0.01)
