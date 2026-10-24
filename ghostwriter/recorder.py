"""Microphone capture that opens on key press and closes on release, so the mic is only live while dictating."""

import time

import numpy as np
import sounddevice as sd

from ghostwriter.transcriber import SAMPLE_RATE

# Keep listening this long after release so the last word isn't clipped.
TAIL_SECONDS = 0.3


class Recorder:
    def __init__(self, tail_seconds: float = TAIL_SECONDS) -> None:
        self.tail_seconds = tail_seconds
        self.open_ms = 0.0
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []

    def start(self) -> None:
        started = time.perf_counter()
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            latency="low",
            callback=self._on_audio,
        )
        self._stream.start()
        self.open_ms = (time.perf_counter() - started) * 1000

    def stop(self) -> np.ndarray:
        """Record the tail, close the mic, and return everything heard as 16 kHz mono float32."""
        time.sleep(self.tail_seconds)
        self._stream.stop()
        self._stream.close()
        self._stream = None
        return np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)

    def _on_audio(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        self._chunks.append(indata[:, 0].copy())
