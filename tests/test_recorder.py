"""The mic opens fast on demand, records while held, and stops listening soon after you go quiet."""

import time

import numpy as np

from ghostwriter.recorder import QUIET_RMS, TAIL_SECONDS, Recorder
from ghostwriter.transcriber import SAMPLE_RATE

HOLD_SECONDS = 0.5
MAX_OPEN_MS = 150


def test_recorder_opens_quickly_and_never_listens_past_the_tail():
    recorder = Recorder()
    recorder.start()
    time.sleep(HOLD_SECONDS)
    stopping = time.perf_counter()
    audio = recorder.stop()
    tail = time.perf_counter() - stopping
    assert recorder.open_ms < MAX_OPEN_MS
    assert audio.dtype.name == "float32"
    assert tail <= TAIL_SECONDS + 0.05
    assert HOLD_SECONDS * SAMPLE_RATE * 0.9 < len(audio) < (HOLD_SECONDS + TAIL_SECONDS + 0.1) * SAMPLE_RATE


def _recorder_that_heard(*levels: float) -> Recorder:
    """A recorder fed 20 ms chunks at the given loudness, without touching the mic."""
    recorder = Recorder()
    chunk = int(0.02 * SAMPLE_RATE)
    recorder._chunks = [np.full(chunk, level, dtype=np.float32) for level in levels]
    return recorder


def test_the_tail_ends_once_the_last_moments_are_quiet():
    speech, silence = QUIET_RMS * 30, QUIET_RMS / 30
    assert _recorder_that_heard(speech, speech, silence, silence, silence).ends_quietly()
    assert not _recorder_that_heard(speech, speech, speech, silence, silence).ends_quietly()
    assert not _recorder_that_heard(silence).ends_quietly()  # too little audio to judge yet
