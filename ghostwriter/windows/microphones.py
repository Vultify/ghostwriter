"""The mics Windows has turned on, found through MME, the audio system Ghostwriter records through on Windows."""

import contextlib
import logging
from collections.abc import Iterator

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


@contextlib.contextmanager
def recording_from(microphone: str | None) -> Iterator[int | None]:
    """The device number to open for a mic, or None for the system default."""
    index = None if microphone is None else microphones().get(microphone)
    if microphone is not None and index is None:
        log.warning("Mic %r isn't connected, using the %s default", microphone, desktop.NAME)
    yield index
