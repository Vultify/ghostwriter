"""Text really lands in another window, and the full press, talk, release loop works end to end."""

import tempfile
import time
from pathlib import Path

import pytest
from conftest import GuardedPaster, press_key, pump_until, run_in_thread, speak_to_wav, text_of
from faster_whisper import decode_audio

from ghostwriter import win32
from ghostwriter.app import Dictation
from ghostwriter.clipboard import Clipboard
from ghostwriter.transcriber import SAMPLE_RATE
from ghostwriter.win32 import user32

SENTENCE = "Book the ceramic coating for Friday morning in Tulare."
RAMBLE = (
    "Okay so here is my plan for the weekend. On Saturday morning I have three ceramic coatings booked, "
    "and the first one is a black truck that needs a full paint correction before the coating goes on. "
    "After that I want to clean the shop, restock the microfiber towels, and order more iron remover. "
    "In the afternoon I will update the booking page and check that the payments are syncing. "
    "Then on Sunday I am going to relax and play some games with my friends. "
    "We have been playing Wardogs a lot lately and our base keeps getting destroyed by missiles. "
    "I think we need to put a sea whiz on every corner of the base, and maybe two sea whizzes near the command center. "
    "Wardogs is way more fun when the defenses actually hold. That is basically the whole plan."
)


def _set_clipboard_text(text: str) -> None:
    Clipboard().restore([(win32.CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))], user32.GetClipboardSequenceNumber())


def test_paste_lands_in_the_focused_window_and_restores_the_clipboard(text_box):
    root, box = text_box
    _set_clipboard_text("what the user had copied")
    paster = GuardedPaster(root.test_window)
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


def _speak(text: str):
    clip = Path(tempfile.gettempdir()) / "ghostwriter_loop_test.wav"
    speak_to_wav(text, clip)
    audio = decode_audio(str(clip), sampling_rate=SAMPLE_RATE)
    clip.unlink(missing_ok=True)
    return audio


@pytest.fixture(scope="module")
def spoken_sentence():
    return _speak(SENTENCE)


@pytest.fixture(scope="module")
def spoken_ramble():
    return _speak(RAMBLE)


def _dictation(transcriber, audio, root) -> Dictation:
    dictation = Dictation(transcriber, ClipRecorder(audio), GuardedPaster(root.test_window), allow_injected=True)
    dictation.start()
    return dictation


def test_hold_right_alt_talk_release_types_the_sentence(transcriber, spoken_sentence, text_box):
    root, box = text_box
    dictation = _dictation(transcriber, spoken_sentence, root)
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


def test_lock_mode_types_a_long_ramble_completely(transcriber, spoken_ramble, text_box):
    root, box = text_box
    dictation = _dictation(transcriber, spoken_ramble, root)
    try:
        # Double tap to lock on, let go for a bit, then tap once to stop.
        for release, wait in ((False, 0.05), (True, 0.1), (False, 0.05), (True, 0.6), (False, 0.05), (True, 0)):
            press_key(win32.VK_RMENU, release=release)
            pump_until(root, lambda: False, timeout=wait)
        pump_until(root, lambda: "whole plan" in box.get("1.0", "end"), timeout=30)
        typed = box.get("1.0", "end-1c")
    finally:
        dictation.stop()
    assert "here is my plan for the weekend" in typed
    assert "Saturday morning" in typed
    assert typed.count("Wardogs") == 2
    assert "CIWS" in typed
    assert "whole plan" in typed


def test_a_quick_tap_types_nothing(text_box, spoken_sentence):
    root, box = text_box
    dictation = _dictation(None, spoken_sentence, root)
    try:
        press_key(win32.VK_RMENU)
        press_key(win32.VK_RMENU, release=True)
        pump_until(root, lambda: False, timeout=1.0)
    finally:
        dictation.stop()
    assert box.get("1.0", "end-1c") == ""
