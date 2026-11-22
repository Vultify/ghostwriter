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


def test_importing_a_big_file_writes_the_dictionary_once(tmp_path, monkeypatch):
    path = tmp_path / "dictionary.txt"
    path.write_text("Ghostwriter\n", encoding="utf-8")
    dictionary = DictionaryFile(path, starter=None)
    writes = []
    real_write = Path.write_text
    monkeypatch.setattr(Path, "write_text", lambda self, *args, **kwargs: writes.append(self) or real_write(self, *args, **kwargs))
    lines = [f"Word{number}" for number in range(500)] + ["Word1", "ghost writer -> Ghostwriter", "Ghostwriter"]
    assert dictionary.merge("\n".join(lines)) == (500, 1)  # a line repeated in the file counts once
    assert writes == [path]
    assert path.read_text(encoding="utf-8").splitlines()[-1] == "ghost writer -> Ghostwriter"


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


def test_an_edit_in_the_same_clock_tick_still_applies(tmp_path):
    path = tmp_path / "dictionary.txt"
    path.write_text("Ghostwriter\n", encoding="utf-8")
    dictionary = DictionaryFile(path, starter=None)
    assert dictionary.current().words == ["Ghostwriter"]
    stamp = path.stat().st_mtime_ns
    path.write_text("Ghostwriter\nBrightwater\n", encoding="utf-8")
    os.utime(path, ns=(stamp, stamp))
    assert dictionary.current().words == ["Ghostwriter", "Brightwater"]


def test_a_dictionary_that_cant_be_read_keeps_the_last_version(tmp_path):
    path = tmp_path / "dictionary.txt"
    path.write_text("Ghostwriter\n", encoding="utf-8")
    dictionary = DictionaryFile(path, starter=None)
    assert dictionary.current().words == ["Ghostwriter"]
    path.write_bytes("Caf\xe9\n".encode("latin-1"))  # saved in the wrong encoding
    assert dictionary.current().words == ["Ghostwriter"]
    path.write_text("Ghostwriter\nCaf\u00e9\n", encoding="utf-8")
    assert dictionary.current().words == ["Ghostwriter", "Caf\u00e9"]


def test_a_fix_needs_a_letter_or_number_in_what_it_hears(tmp_path):
    path = tmp_path / "dictionary.txt"
    path.write_text("Ghostwriter\n", encoding="utf-8")
    dictionary = DictionaryFile(path, starter=None)
    for heard in ("\u2026", "?!", "ok, ?!"):
        with pytest.raises(ValueError, match="letter or number"):
            dictionary.add_fix(heard, "...")
    assert Dictionary.parse("?! -> nope\nsea whiz, \u2026 -> CIWS\n").apply("hello sea whiz there") == "hello CIWS there"


def test_the_window_side_reads_a_badly_saved_dictionary_as_a_plain_error(tmp_path):
    path = tmp_path / "dictionary.txt"
    path.write_bytes("Caf\xe9\n".encode("latin-1"))
    dictionary = DictionaryFile(path, starter=None)
    with pytest.raises(ValueError, match="UTF-8"):
        dictionary.entries()
