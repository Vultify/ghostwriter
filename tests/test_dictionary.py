"""The dictionary file: words and fix rules parse right, fixes are safe, and every word comes out right when spoken."""

import os
import tempfile
from pathlib import Path

import pytest
from conftest import speak_to_wav
from faster_whisper import decode_audio

from ghostwriter.dictionary import Dictionary, DictionaryFile
from ghostwriter.transcriber import SAMPLE_RATE

EXAMPLE = """
# a comment
Tulare
C#

sea whiz, sea whizzes, CWIS -> CIWS
"""


def test_words_and_fixes_are_read_and_comments_skipped():
    dictionary = Dictionary.parse(EXAMPLE)
    assert dictionary.words == ["Tulare", "C#", "CIWS"]
    assert len(dictionary.fixes) == 3
    assert dictionary.prompt == "Tulare, C#, CIWS."


@pytest.mark.parametrize("heard", ["sea whiz", "Sea Whiz", "sea-whiz", "seawhiz", "Sea whizzes", "CWIS"])
def test_fixes_match_loosely(heard):
    assert Dictionary.parse(EXAMPLE).apply(f"I built a {heard}.") == "I built a CIWS."


def test_fixes_leave_other_words_alone():
    text = "The sea was calm and he is a whiz at math, a seawhizard."
    assert Dictionary.parse(EXAMPLE).apply(text) == text


def test_an_empty_dictionary_changes_nothing():
    dictionary = Dictionary.parse("")
    assert dictionary.prompt is None
    assert dictionary.apply("sea whiz") == "sea whiz"


def test_file_changes_apply_without_a_restart(tmp_path):
    path = tmp_path / "dictionary.txt"
    path.write_text("Tulare\n", encoding="utf-8")
    dictionary = DictionaryFile(path)
    assert dictionary.current().words == ["Tulare"]
    path.write_text("Tulare\nWardogs\n", encoding="utf-8")
    later = path.stat().st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(later, later))  # make sure the change is seen even on a coarse file clock
    assert dictionary.current().words == ["Tulare", "Wardogs"]


def test_a_missing_file_means_an_empty_dictionary(tmp_path):
    assert DictionaryFile(tmp_path / "missing.txt").current().words == []


SPOKEN = [
    ("I'm testing Ghostwriter right now.", "Ghostwriter"),
    # The robot voice slurs "in Tulare" at the end of very short sentences ("into Lairi"); real speech is fine.
    ("Our shop is in Tulare, California.", "Tulare"),
    ("Castro Detailing is open on Saturday.", "Castro Detailing"),
    ("The bookings are stored in Supabase.", "Supabase"),
    ("I asked Claude Code to fix the bug.", "Claude Code"),
    ("I played Wardogs last night.", "Wardogs"),
    ("I put a sea whiz on the corner of my base.", "CIWS"),
    ("Should I build two sea whizzes or one?", "CIWS"),
]


@pytest.mark.parametrize(("sentence", "expected"), SPOKEN)
def test_every_dictionary_word_comes_out_right_when_spoken(transcriber, sentence, expected):
    clip = Path(tempfile.gettempdir()) / "ghostwriter_dictionary_test.wav"
    speak_to_wav(sentence, clip)
    audio = decode_audio(str(clip), sampling_rate=SAMPLE_RATE)
    clip.unlink(missing_ok=True)
    dictionary = DictionaryFile().current()
    heard = dictionary.apply(transcriber.transcribe(audio, prompt=dictionary.prompt))
    assert expected in heard
