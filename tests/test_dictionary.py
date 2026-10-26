"""The dictionary file: words and fix rules parse right, fixes are safe, and every word comes out right when spoken."""

import os
import tempfile
from pathlib import Path

import pytest
from conftest import fixed_dictionary, speak_to_wav
from faster_whisper import decode_audio

from ghostwriter.dictionary import STARTER_PATH, Dictionary, DictionaryFile
from ghostwriter.transcriber import SAMPLE_RATE

EXAMPLE = """
# a comment
Gloucester
C#

my sequel, my SQL, MySequel -> MySQL
"""


def test_words_and_fixes_are_read_and_comments_skipped():
    dictionary = Dictionary.parse(EXAMPLE)
    assert dictionary.words == ["Gloucester", "C#", "MySQL"]
    assert len(dictionary.fixes) == 3
    assert dictionary.prompt == "Gloucester, C#, MySQL."


@pytest.mark.parametrize("heard", ["my sequel", "My Sequel", "my-sequel", "mysequel", "my SQL", "My Sql"])
def test_fixes_match_loosely(heard):
    assert Dictionary.parse(EXAMPLE).apply(f"I set up a {heard} database.") == "I set up a MySQL database."


def test_fixes_leave_other_words_alone():
    text = "My sequels are better than the originals, and mysequelwriter is a username."
    assert Dictionary.parse(EXAMPLE).apply(text) == text


def test_an_empty_dictionary_changes_nothing():
    dictionary = Dictionary.parse("")
    assert dictionary.prompt is None
    assert dictionary.apply("my sequel") == "my sequel"


def test_file_changes_apply_without_a_restart(tmp_path):
    path = tmp_path / "dictionary.txt"
    path.write_text("Gloucester\n", encoding="utf-8")
    dictionary = DictionaryFile(path)
    assert dictionary.current().words == ["Gloucester"]
    path.write_text("Gloucester\nBrightwater\n", encoding="utf-8")
    later = path.stat().st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(later, later))  # make sure the change is seen even on a coarse file clock
    assert dictionary.current().words == ["Gloucester", "Brightwater"]


def test_a_missing_file_means_an_empty_dictionary(tmp_path):
    assert DictionaryFile(tmp_path / "missing.txt", starter=None).current().words == []


def test_a_new_user_gets_the_starter_dictionary(tmp_path):
    path = tmp_path / "dictionary.txt"
    starter = DictionaryFile(path).current()
    assert path.read_text(encoding="utf-8") == STARTER_PATH.read_text(encoding="utf-8")
    assert {"Ghostwriter", "GitHub", "VS Code", "Discord"} <= set(starter.words)
    assert starter.fixes == []  # the fix examples are notes until someone turns them on


SPOKEN = [
    ("I'm testing Ghostwriter right now.", "Ghostwriter"),
    ("Our shop is in Gloucester, Massachusetts.", "Gloucester"),
    ("Brightwater Detailing is open on Saturday.", "Brightwater Detailing"),
    ("The bookings are stored in Supabase.", "Supabase"),
    ("I asked Claude Code to fix the bug.", "Claude Code"),
    ("I built Ghostwriter to replace Whisper Flow.", "Wispr Flow"),
    ("We keep the bookings in a my sequel database.", "MySQL"),
    ("Should we spin up two my sequel servers or one?", "MySQL"),
]


@pytest.mark.parametrize(("sentence", "expected"), SPOKEN)
def test_every_dictionary_word_comes_out_right_when_spoken(transcriber, sentence, expected):
    clip = Path(tempfile.gettempdir()) / "ghostwriter_dictionary_test.wav"
    speak_to_wav(sentence, clip)
    audio = decode_audio(str(clip), sampling_rate=SAMPLE_RATE)
    clip.unlink(missing_ok=True)
    dictionary = fixed_dictionary().current()
    heard = dictionary.apply(transcriber.transcribe(audio, prompt=dictionary.prompt))
    assert expected in heard
