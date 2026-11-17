"""The mics Windows has turned on, found through MME, the audio system Ghostwriter records through on Windows."""

import logging
from collections.abc import Callable

import sounddevice as sd

from ghostwriter.windows import desktop

log = logging.getLogger("ghostwriter")


def microphones() -> dict[str, int]:
    """Map each mic's full name to its device number in MME."""
    apis = sd.query_hostapis()
    devices = sd.query_devices()
    inputs = [(index, device) for index, device in enumerate(devices) if device["max_input_channels"] > 0]
    # MME cuts names off at 31 characters, so borrow the full name from DirectSound when one starts the same way.
    full_names = [device["name"] for _, device in inputs if apis[device["hostapi"]]["name"] == "Windows DirectSound"]
    found = {}
    for index, device in inputs:
        name = device["name"]
        if apis[device["hostapi"]]["name"] != "MME" or name.startswith("Microsoft Sound Mapper"):
            continue
        found[next((full for full in full_names if full.startswith(name)), name)] = index
    return found


def open_stream(microphone: str | None, samplerate: int, callback: Callable) -> sd.InputStream:
    """A mono float32 recording from a mic, or the system default for None. The caller starts it."""
    index = None if microphone is None else microphones().get(microphone)
    if microphone is not None and index is None:
        log.warning("Mic %r isn't connected, using the %s default", microphone, desktop.NAME)
    return sd.InputStream(samplerate=samplerate, channels=1, dtype="float32", latency="low", device=index,
                          callback=callback)
