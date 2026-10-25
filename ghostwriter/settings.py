"""Ghostwriter's settings, changed from the tray menu and kept in settings.json in the project folder."""

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ghostwriter import win32

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"

# Single keys that make good hotkeys: easy to reach and rarely needed on their own.
HOTKEYS = {
    "Right Alt": win32.VK_RMENU,
    "Right Ctrl": win32.VK_RCONTROL,
    "Caps Lock": win32.VK_CAPITAL,
    "Scroll Lock": win32.VK_SCROLL,
    "Pause": win32.VK_PAUSE,
}
DEFAULT_HOTKEY = "Right Alt"

log = logging.getLogger("ghostwriter")


@dataclass
class Settings:
    hotkey: str = DEFAULT_HOTKEY
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
