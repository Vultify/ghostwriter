"""Audio format shared by the mic and Whisper, kept apart so the app window can list mics without loading Whisper."""

import io
import math
import wave

import numpy as np

SAMPLE_RATE = 16000  # Whisper listens at 16 kHz mono

# Mic loudness range shown on the listening pill and the mic test, from room quiet to normal speaking.
QUIET_DB, LOUD_DB = -55.0, -15.0


def loudness(rms: float) -> float:
    """Map a mic RMS level onto 0 to 1 for level bars."""
    db = 20 * math.log10(max(rms, 1e-9))
    return min(1.0, max(0.0, (db - QUIET_DB) / (LOUD_DB - QUIET_DB)))


def wav_bytes(audio: np.ndarray) -> bytes:
    """16 kHz mono float32 audio as a 16 bit WAV file."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(SAMPLE_RATE)
        file.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return buffer.getvalue()
