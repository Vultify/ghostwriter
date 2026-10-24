"""What Ghostwriter is doing right now, shown by the tray icon, the listening pill, and the sounds."""

from enum import Enum


class State(Enum):
    READY = "ready"
    LISTENING = "listening"
    LOCKED = "locked"  # listening hands free after a double tap
    WORKING = "working"

    @property
    def is_recording(self) -> bool:
        return self in (State.LISTENING, State.LOCKED)
