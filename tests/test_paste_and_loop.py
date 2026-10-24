"""Text really lands in another window, and the full press, talk, release loop works end to end."""

import tempfile
import time
from pathlib import Path

import pytest
from conftest import press_key, pump_until, run_in_thread, speak_to_wav, text_of
from faster_whisper import decode_audio

from ghostwriter import win32
from ghostwriter.app import Dictation
from ghostwriter.clipboard import Clipboard
from ghostwriter.paster import Paster
from ghostwriter.transcriber import SAMPLE_RATE, Transcriber
from ghostwriter.win32 import user32

SENTENCE = "Book the ceramic coating for Friday morning in Tulare."


def _set_clipboard_text(text: str) -> None:
    Clipboard().restore([(win32.CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))], user32.GetClipboardSequenceNumber())


def test_paste_lands_in_the_focused_window_and_restores_the_clipboard(text_box):
    root, box = text_box
    _set_clipboard_text("what the user had copied")
    paster = Paster()
    result = {}
    worker = run_in_thread(lambda: result.update(restored=paster.paste("Hello from Ghostwriter. ")))
    pump_until(root, lambda: not worker.is_alive())
    assert box.get("1.0", "end-1c") == "Hello from Ghostwriter. "
    assert result["restored"]
    assert text_of(Clipboard().snapshot()) == "what the user had copied"


class ClipRecorder:
    """Stands in for the mic and plays back a recorded sentence instead."""

    def __init__(self, audio) -> None:
        self.audio = audio
        self.open_ms = 0.0

    def start(self) -> None:
        pass

    def stop(self):
        return self.audio


@pytest.fixture(scope="module")
def transcriber():
    # Loaded before the test window opens, so the window never sits frozen while Whisper loads.
    model = Transcriber()
    model.warm_up()
    return model


@pytest.fixture(scope="module")
def spoken_sentence():
    clip = Path(tempfile.gettempdir()) / "ghostwriter_loop_test.wav"
    speak_to_wav(SENTENCE, clip)
    audio = decode_audio(str(clip), sampling_rate=SAMPLE_RATE)
    clip.unlink(missing_ok=True)
    return audio


def test_hold_right_alt_talk_release_types_the_sentence(transcriber, spoken_sentence, text_box):
    root, box = text_box
    dictation = Dictation(transcriber, ClipRecorder(spoken_sentence), Paster(), allow_injected=True)
    dictation.start()
    try:
        press_key(win32.VK_RMENU)
        pump_until(root, lambda: False, timeout=0.4)
        press_key(win32.VK_RMENU, release=True)
        pump_until(root, lambda: "Tulare" in box.get("1.0", "end"))
        typed = box.get("1.0", "end-1c")
    finally:
        dictation.stop()
    assert "ceramic coating" in typed.lower()
    assert "Tulare" in typed
    assert typed.endswith(" ")


def test_a_quick_tap_types_nothing(text_box, spoken_sentence):
    root, box = text_box
    dictation = Dictation(None, ClipRecorder(spoken_sentence), Paster(), allow_injected=True)
    dictation.start()
    try:
        press_key(win32.VK_RMENU)
        press_key(win32.VK_RMENU, release=True)
        pump_until(root, lambda: False, timeout=1.0)
    finally:
        dictation.stop()
    assert box.get("1.0", "end-1c") == ""
