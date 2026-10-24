"""The mic opens fast on demand and records for as long as it's held, plus the tail."""

import time

from ghostwriter.recorder import TAIL_SECONDS, Recorder
from ghostwriter.transcriber import SAMPLE_RATE

HOLD_SECONDS = 0.5
MAX_OPEN_MS = 150


def test_recorder_opens_quickly_and_keeps_the_tail():
    recorder = Recorder()
    recorder.start()
    time.sleep(HOLD_SECONDS)
    audio = recorder.stop()
    expected = (HOLD_SECONDS + TAIL_SECONDS) * SAMPLE_RATE
    assert recorder.open_ms < MAX_OPEN_MS
    assert audio.dtype.name == "float32"
    assert abs(len(audio) - expected) < 0.1 * SAMPLE_RATE
