"""Ghostwriter's settings, changed from the tray menu and kept in settings.json in the project folder."""

import json
import logging
from dataclasses import asdict, dataclass, field
from ctypes import wintypes
from pathlib import Path

from ghostwriter import win32
from ghostwriter.win32 import user32

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"

# Single keys that make good hotkeys: easy to reach and rarely needed on their own.
HOTKEYS = {
    "Right Alt": win32.VK_RMENU,
    "Right Ctrl": win32.VK_RCONTROL,
    "Caps Lock": win32.VK_CAPITAL,
    "Scroll Lock": win32.VK_SCROLL,
    "Pause": win32.VK_PAUSE,
}
# Characters that keyboards with an AltGr key (Right Alt on most non-US layouts) type through it.
_ALTGR_CHARACTERS = "@€{}[]\\|~#$^`<>"
_CTRL_AND_ALT = 0x06  # in the shift state VkKeyScanEx reports

log = logging.getLogger("ghostwriter")


def keyboard_uses_altgr() -> bool:
    """Whether any installed keyboard layout types characters with AltGr, which would make Right Alt a bad hotkey."""
    count = user32.GetKeyboardLayoutList(0, None)
    layouts = (wintypes.HKL * count)()
    user32.GetKeyboardLayoutList(count, layouts)
    for layout in layouts:
        for character in _ALTGR_CHARACTERS:
            key = user32.VkKeyScanExW(character, layout)
            if key != -1 and (key >> 8) & _CTRL_AND_ALT == _CTRL_AND_ALT:
                return True
    return False


def default_hotkey() -> str:
    return "Right Ctrl" if keyboard_uses_altgr() else "Right Alt"


@dataclass
class Settings:
    hotkey: str = field(default_factory=default_hotkey)
    microphone: str | None = None  # None follows the Windows default mic
    sounds: bool = True
    path: Path = field(default=SETTINGS_PATH, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> "Settings":
        """Read the settings file, keeping defaults for anything missing or unreadable."""
        settings = cls(path=path)
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return settings
        except (OSError, ValueError) as error:
            log.warning("Ignoring unreadable %s: %s", path.name, error)
            return settings
        if saved.get("hotkey") in HOTKEYS:
            settings.hotkey = saved["hotkey"]
        if isinstance(saved.get("microphone"), str):
            settings.microphone = saved["microphone"]
        if isinstance(saved.get("sounds"), bool):
            settings.sounds = saved["sounds"]
        return settings

    @property
    def hotkey_code(self) -> int:
        return HOTKEYS[self.hotkey]

    def save(self) -> None:
        values = {key: value for key, value in asdict(self).items() if key != "path"}
        self.path.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
