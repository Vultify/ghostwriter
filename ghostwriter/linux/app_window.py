"""The app window's Linux parts. The window comes to Linux in a later step (WebKitGTK), so for now opening it only
notes that in the log, and the settings are in the tray menu."""

import logging

WEB_ENGINE = "gtk"  # pywebview's name for WebKitGTK
MISSING_ENGINE_MESSAGE = (
    "Ghostwriter's window needs WebKitGTK (webkit2gtk-4.1), and it isn't installed.\n\n"
    "Dictation still works: use the ghost in the tray."
)

log = logging.getLogger("ghostwriter")


def open_window() -> None:
    log.info("The app window isn't on Linux yet, so the settings are in the tray menu")


def close_window(title: str) -> None:
    """No window to close yet."""


def bring_to_front(title: str) -> None:
    """No window to bring forward yet."""


def style_frame(window, width: int, height: int) -> None:
    """The desktop draws the frame on Linux."""
