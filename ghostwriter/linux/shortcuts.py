"""Starting Ghostwriter at login on Linux comes in a later step (Hyprland autostart and a launcher entry), so for now
it stays off and the switch in the app window does nothing."""

import logging
from pathlib import Path

log = logging.getLogger("ghostwriter")


def starts_at_login(folder: Path | None = None) -> bool:
    return False


def set_start_at_login(on: bool, folder: Path | None = None) -> None:
    log.info("Start at login isn't on Linux yet, so it stays off")
