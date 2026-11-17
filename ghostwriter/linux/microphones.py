"""The mics on Linux, and recordings from them, through PulseAudio's client library. PipeWire serves the same
library, so this works on both, and it's how browsers and chat apps pick a mic: by name, per recording. The names
shown are the ones the desktop's sound settings use."""

import ctypes
import json
import logging
import subprocess
import threading
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from ghostwriter.linux import desktop

CHUNK_SECONDS = 0.01  # how much audio each read hands over

log = logging.getLogger("ghostwriter")


def microphones() -> dict[str, str]:
    """Map each mic's name to the name PulseAudio opens it by. Empty without PulseAudio or PipeWire, so only the
    system default is offered."""
    try:
        sources = json.loads(subprocess.run(["pactl", "--format=json", "list", "sources"], capture_output=True,
                                            text=True, timeout=2, check=True).stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    mics = [(source.get("description") or source["name"], source["name"]) for source in sources
            if source.get("name") and (source.get("properties") or {}).get("device.class") != "monitor"]  # not speakers
    labels, taken = {}, set()
    # Two of the same mic are numbered in order of their names, which stay put when they're plugged back in.
    for description, name in sorted(mics, key=lambda mic: mic[1]):
        label, number = description, 2
        while label in taken:
            label, number = f"{description} ({number})", number + 1
        taken.add(label)
        labels[name] = label
    return {labels[name]: name for _, name in mics}


def open_stream(microphone: str | None, samplerate: int, callback: Callable) -> "PulseStream | sd.InputStream":
    """A mono float32 recording from a mic, or the system default for None, handing each chunk to callback the way
    a sounddevice stream does. Without PulseAudio's library, it records from the default through sounddevice."""
    source = None
    if microphone is not None:
        # Looked up each time: a mic's name changes with its profile, and PulseAudio quietly opens the default for
        # a name it doesn't know, so this is the only way to notice a mic that's gone.
        source = microphones().get(microphone)
        if source is None:
            log.warning("Mic %r isn't connected, using the %s default", microphone, desktop.NAME)
    try:
        return PulseStream(source, samplerate, callback)
    except OSError as error:
        log.warning("Recording from sounddevice's default mic, since PulseAudio couldn't open one: %s", error)
        return sd.InputStream(samplerate=samplerate, channels=1, dtype="float32", latency="low", callback=callback)


class _SampleSpec(ctypes.Structure):
    _fields_ = [("format", ctypes.c_int), ("rate", ctypes.c_uint32), ("channels", ctypes.c_uint8)]


class _BufferAttributes(ctypes.Structure):
    _fields_ = [(field, ctypes.c_uint32) for field in ("maxlength", "tlength", "prebuf", "minreq", "fragsize")]


_FLOAT32LE = 5  # PA_SAMPLE_FLOAT32LE
_RECORD = 2  # PA_STREAM_RECORD
_SERVER_DEFAULT = 0xFFFFFFFF  # (uint32_t) -1: let the server choose
_NO_LATENCY = 2 ** 64 - 1  # (pa_usec_t) -1: the latency isn't known yet
_library = None


def _pulse() -> ctypes.CDLL:
    global _library
    if _library is None:
        library = ctypes.CDLL("libpulse-simple.so.0")
        library.pa_simple_new.restype = ctypes.c_void_p
        library.pa_simple_new.argtypes = [
            ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p,
            ctypes.POINTER(_SampleSpec), ctypes.c_void_p, ctypes.POINTER(_BufferAttributes),
            ctypes.POINTER(ctypes.c_int)]
        library.pa_simple_read.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                           ctypes.POINTER(ctypes.c_int)]
        library.pa_simple_free.argtypes = [ctypes.c_void_p]
        library.pa_simple_get_latency.restype = ctypes.c_uint64
        library.pa_simple_get_latency.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        library.pa_strerror.restype = ctypes.c_char_p
        library.pa_strerror.argtypes = [ctypes.c_int]
        _library = library
    return _library


class PulseStream:
    """A recording from one mic. PulseAudio starts capturing as soon as it opens; start() hands the audio to the
    callback from a thread of its own, CHUNK_SECONDS at a time."""

    def __init__(self, source: str | None, samplerate: int, callback: Callable) -> None:
        library = _pulse()
        self._frames = round(samplerate * CHUNK_SECONDS)
        self.latency = CHUNK_SECONDS  # until PulseAudio knows how far behind the mic the reads are
        self._callback = callback
        self._reading = threading.Event()
        self._reader: threading.Thread | None = None
        self._reader_done = False
        self._closed = False
        self._lock = threading.Lock()  # between close() and a reader that outlived it, so the handle is freed once
        chunk_bytes = self._frames * 4
        error = ctypes.c_int()
        self._handle = library.pa_simple_new(
            None, b"Ghostwriter", _RECORD, source.encode() if source else None, b"Dictation",
            ctypes.byref(_SampleSpec(_FLOAT32LE, samplerate, 1)), None,
            ctypes.byref(_BufferAttributes(_SERVER_DEFAULT, _SERVER_DEFAULT, _SERVER_DEFAULT, _SERVER_DEFAULT,
                                           chunk_bytes)),
            ctypes.byref(error))
        if not self._handle:
            raise OSError(f"couldn't open the mic: {library.pa_strerror(error.value).decode()}")

    def start(self) -> None:
        self._reading.set()
        self._reader = threading.Thread(target=self._read, name="Mic", daemon=True)
        self._reader.start()

    def stop(self) -> None:
        self._reading.clear()
        if self._reader is not None:
            self._reader.join(timeout=1)  # a read ends within one chunk, unless the sound server hangs

    def close(self) -> None:
        self.stop()
        with self._lock:
            self._closed = True
            if self._reader is not None and not self._reader_done:
                # Freeing it mid-read would crash, so the reader frees it when the sound server lets go.
                log.warning("The mic didn't stop in time, so it closes once the sound server answers")
                return
            self._free()

    def _free(self) -> None:
        if self._handle:
            _pulse().pa_simple_free(self._handle)
            self._handle = None

    def _read(self) -> None:
        library = _pulse()
        chunk = np.empty((self._frames, 1), dtype=np.float32)
        error = ctypes.c_int()
        try:
            while self._reading.is_set():
                if library.pa_simple_read(self._handle, chunk.ctypes.data, chunk.nbytes, ctypes.byref(error)) < 0:
                    log.warning("The mic stopped: %s", library.pa_strerror(error.value).decode())
                    return
                if not self._reading.is_set():  # stopped while waiting, so this audio belongs to no recording
                    return
                try:
                    self._callback(chunk, self._frames, None, None)
                except Exception:
                    log.exception("The recording couldn't take the mic's audio")
                    return
                behind = library.pa_simple_get_latency(self._handle, ctypes.byref(error))
                if behind != _NO_LATENCY:
                    self.latency = CHUNK_SECONDS + behind / 1_000_000
        finally:
            with self._lock:
                self._reader_done = True
                if self._closed:
                    self._free()
