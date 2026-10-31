"""Audio format shared by the mic and Whisper, kept apart so the app window can list mics without loading Whisper."""

import math

SAMPLE_RATE = 16000  # Whisper listens at 16 kHz mono

# Mic loudness range shown on the listening pill and the mic test, from room quiet to normal speaking.
QUIET_DB, LOUD_DB = -55.0, -15.0


def loudness(rms: float) -> float:
    """Map a mic RMS level onto 0 to 1 for level bars."""
    db = 20 * math.log10(max(rms, 1e-9))
    return min(1.0, max(0.0, (db - QUIET_DB) / (LOUD_DB - QUIET_DB)))
