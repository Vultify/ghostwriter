"""The tray ghost on Windows is pystray's own notification area icon; ghostwriter.tray builds its menu."""

from pystray import Icon

__all__ = ["DICTATION_SWITCH", "Icon", "publish"]

DICTATION_SWITCH = False  # dictation is always on with Windows, so its menu has no Dictation switch


def publish(status: dict) -> None:
    """Windows has no bar panel to keep up to date."""
