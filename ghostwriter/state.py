"""What Ghostwriter is doing right now, shown by the tray icon, the listening pill, and the sounds."""

from enum import Enum


class State(Enum):
    READY = "ready"
    LISTENING = "listening"
    WORKING = "working"
