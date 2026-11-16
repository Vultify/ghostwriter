"""Starting Ghostwriter at login on Linux comes in a later step (Hyprland autostart and a launcher entry), so for now
it's always off."""

from pathlib import Path


def starts_at_login(folder: Path | None = None) -> bool:
    return False


def set_start_at_login(on: bool, folder: Path | None = None) -> None:
    raise NotImplementedError("Start at login comes to Linux in a later step")
