"""The tray ghost on Windows is pystray's own notification area icon; ghostwriter.tray builds its menu."""

from pystray import Icon

__all__ = ["Icon", "publish"]


def publish(status: dict) -> None:
    """Windows has no bar panel to keep up to date."""
