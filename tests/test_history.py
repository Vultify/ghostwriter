"""Dictation history: saving, searching, the counts on Home, clearing, and naming the app each dictation went to."""

from datetime import date, datetime
from pathlib import Path

import numpy as np
import pytest
from conftest import fixed_dictionary
from test_status import FakePaster, FakeRecorder, FakeTranscriber

from ghostwriter.app import Dictation
from ghostwriter.audio import SAMPLE_RATE
from ghostwriter.history import FILTER_APPS, History
from ghostwriter.paster import PasteError, app_name
from ghostwriter.paths import PROJECT

TWO_SECONDS = np.zeros(SAMPLE_RATE * 2, dtype=np.float32)


@pytest.fixture
def history(tmp_path):
    return History(tmp_path / "history.db")


def test_dictations_come_back_newest_first_with_their_details(history):
    history.add("Book the coating for Friday.", "Google Chrome", 2.04, at=datetime(2026, 10, 27, 9, 30))
    history.add("See you then.", "Discord", 1.0, at=datetime(2026, 10, 28, 17, 15, 47))
    result = history.search()
    assert result["total"] == 2
    newest, oldest = result["items"]
    assert (newest["text"], newest["app"], newest["at"], newest["words"]) == ("See you then.", "Discord", "2026-10-28T17:15:47", 3)
    assert (oldest["seconds"], oldest["words"]) == (2.0, 5)


def test_search_finds_words_anywhere_and_takes_symbols_literally(history):
    for text in ("Deploy the MySQL backup", "my sequel", "100% done", "100 percent done", "snake_case name", "snakeXcase"):
        history.add(text, "Notepad", 1.0)
    assert [item["text"] for item in history.search("mysql")["items"]] == ["Deploy the MySQL backup"]
    assert [item["text"] for item in history.search("100%")["items"]] == ["100% done"]
    assert [item["text"] for item in history.search("e_c")["items"]] == ["snake_case name"]
    assert history.search("  ")["total"] == 6


def test_filtering_by_app_and_the_most_used_apps(history):
    for app, times in [("Discord", 3), ("Google Chrome", 2), ("Notepad", 1), ("Steam", 1), ("Word", 1), ("Excel", 1)]:
        for _ in range(times):
            history.add("hello there", app, 1.0)
    assert history.search(app="Google Chrome")["total"] == 2
    assert history.search("hello", app="Discord")["total"] == 3
    apps = history.apps()
    assert len(apps) == FILTER_APPS and apps[:2] == ["Discord", "Google Chrome"]


def test_a_page_of_results_still_reports_the_full_count(history):
    for number in range(5):
        history.add(f"note {number}", "Notepad", 1.0)
    result = history.search(limit=2)
    assert result["total"] == 5
    assert [item["text"] for item in result["items"]] == ["note 4", "note 3"]


def test_home_counts_today_and_this_month(history):
    history.add("last month words here", "Notepad", 1.0, at=datetime(2026, 9, 30, 23, 59))
    history.add("earlier this month", "Notepad", 1.0, at=datetime(2026, 10, 3, 8, 0))
    history.add("one two three", "Discord", 1.0, at=datetime(2026, 10, 28, 0, 0, 5))
    history.add("four five", "Discord", 1.0, at=datetime(2026, 10, 28, 22, 0))
    summary = history.summary(today=date(2026, 10, 28))
    assert (summary["words_today"], summary["dictations_today"], summary["words_month"], summary["total"]) == (5, 2, 8, 4)
    assert [item["text"] for item in summary["recent"]] == ["four five", "one two three", "earlier this month"]


def test_an_empty_history_counts_zero(history):
    summary = history.summary()
    assert (summary["words_today"], summary["dictations_today"], summary["words_month"], summary["recent"]) == (0, 0, 0, [])


def test_clearing_deletes_everything_and_changes_the_stamp(history):
    history.add("a private thought", "Notepad", 1.0)
    before = history.stamp()
    history.clear()
    assert history.search()["total"] == 0
    assert history.stamp() != before
    assert b"private thought" not in history.path.read_bytes()


def test_apps_are_named_the_way_windows_shows_them(tmp_path):
    assert app_name(Path(r"C:\Windows\System32\notepad.exe")) == "Notepad"
    assert app_name(Path(r"C:\Windows\explorer.exe")) == "Windows Explorer"
    assert app_name(PROJECT / ".python" / "pythonw.exe") == "Ghostwriter"
    plain = tmp_path / "Some Tool.exe"
    plain.write_bytes(b"")
    assert app_name(plain) == "Some Tool"
    assert app_name(None) == "Unknown app"


def test_dictations_are_saved_even_when_the_paste_fails(history):
    class BlockedPaster:
        def paste(self, text: str) -> bool:
            raise PasteError("blocked")

    dictation = Dictation(FakeTranscriber(), FakeRecorder(), FakePaster(), dictionary=fixed_dictionary(), history=history)
    dictation._type_out(TWO_SECONDS)
    dictation.paster = BlockedPaster()
    with pytest.raises(PasteError):
        dictation._type_out(TWO_SECONDS)
    dictation.history = None  # history turned off
    dictation.paster = FakePaster()
    dictation._type_out(TWO_SECONDS)
    assert [(item["text"], item["seconds"], item["words"]) for item in history.search()["items"]] == [("hello", 2.0, 1)] * 2
