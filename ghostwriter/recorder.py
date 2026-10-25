"""Microphone capture that opens on key press and closes on release, so the mic is only live while dictating."""

import logging
import time

import numpy as np
import sounddevice as sd

from ghostwriter.transcriber import SAMPLE_RATE

# Keep listening this long after release so the last word isn't clipped.
TAIL_SECONDS = 0.3

log = logging.getLogger("ghostwriter")


class Recorder:
    def __init__(self, tail_seconds: float = TAIL_SECONDS, microphone: str | None = None) -> None:
        self.tail_seconds = tail_seconds
        self.microphone = microphone  # a name from list_microphones(), or None for the Windows default
        self.open_ms = 0.0
        self.level = 0.0  # loudness (RMS) of the latest chunk, for the listening pill
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
            device=_device_index(self.microphone),
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
        self.level = 0.0
        return np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)

    def _on_audio(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        chunk = indata[:, 0].copy()
        self._chunks.append(chunk)
        self.level = float(np.sqrt(np.mean(chunk * chunk)))


def list_microphones() -> list[str]:
    """Names of the mics Windows has turned on, for the tray menu."""
    return list(_microphones())


def _microphones() -> dict[str, int]:
    """Map each mic's full name to its device number in MME, the audio system Ghostwriter records through."""
    apis = sd.query_hostapis()
    devices = sd.query_devices()
    inputs = [(index, device) for index, device in enumerate(devices) if device["max_input_channels"] > 0]
    # MME cuts names off at 31 characters, so borrow the full name from DirectSound when one starts the same way.
    full_names = [device["name"] for _, device in inputs if apis[device["hostapi"]]["name"] == "Windows DirectSound"]
    microphones = {}
    for index, device in inputs:
        name = device["name"]
        if apis[device["hostapi"]]["name"] != "MME" or name.startswith("Microsoft Sound Mapper"):
            continue
        microphones[next((full for full in full_names if full.startswith(name)), name)] = index
    return microphones


def _device_index(microphone: str | None) -> int | None:
    if microphone is None:
        return None
    index = _microphones().get(microphone)
    if index is None:
        log.warning("Mic %r isn't connected, using the Windows default", microphone)
    return index
