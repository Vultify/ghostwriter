"""The app window: what its page can ask Python for, the page itself driven in a real window, and opening it."""

import json
import time
from datetime import datetime, timedelta

import pytest

from ghostwriter import startup, updates, window
from ghostwriter.history import History
from ghostwriter.paths import ICON_PATH, UI_DIR
from ghostwriter.settings import HOTKEYS
from ghostwriter.window import Api

STARTER = "# notes stay put\nGhostwriter\n\n# a section\nsea whiz -> CIWS\n"


@pytest.fixture
def api(tmp_path):
    (tmp_path / "dictionary.txt").write_text(STARTER, encoding="utf-8")
    return Api(settings_path=tmp_path / "settings.json", dictionary_path=tmp_path / "dictionary.txt",
               history_path=tmp_path / "history.db", startup_path=tmp_path / "startup.json")


def test_state_has_everything_the_page_shows(api):
    state = api.state()
    assert state["settings"]["theme"] == "system"
    assert state["settings"]["hands_free"] is True
    assert state["settings"]["history"] is True
    assert state["firstRun"] is False
    assert state["hotkeys"] == list(HOTKEYS)
    assert state["handsFreeMinutes"] == [5, 15, 30]
    assert state["microphones"] and state["gpu"]


def test_settings_save_and_bad_values_are_refused(api, tmp_path):
    api.set_setting("hotkey", "Caps Lock")
    api.set_setting("hands_free_minutes", 30)
    state = api.set_setting("theme", "light")
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert (saved["hotkey"], saved["hands_free_minutes"], saved["theme"]) == ("Caps Lock", 30, "light")
    assert state["settings"]["theme"] == "light"
    for name, value in [("hotkey", "F13"), ("hands_free_minutes", 7), ("theme", "blue"), ("nonsense", 1)]:
        with pytest.raises(ValueError):
            api.set_setting(name, value)


def test_dictionary_edits_keep_the_files_notes(api, tmp_path):
    api.add_word("  Brightwater  ")
    api.add_word("Brightwater")  # a duplicate is ignored
    entries = api.add_fix("my sequel,my SQL", "MySQL")
    assert entries == {"words": ["Ghostwriter", "Brightwater"],
                       "fixes": [{"heard": "sea whiz", "write": "CIWS"}, {"heard": "my sequel, my SQL", "write": "MySQL"}]}
    api.remove_word("Ghostwriter")
    entries = api.remove_fix("sea whiz", "CIWS")
    assert entries["words"] == ["Brightwater"] and len(entries["fixes"]) == 1
    text = (tmp_path / "dictionary.txt").read_text(encoding="utf-8")
    assert text.startswith("# notes stay put\n") and "# a section" in text


def test_dictionary_entries_that_would_break_the_file_are_refused(api):
    for bad in ["", "   ", "a -> b", "# note", "two\nlines"]:
        assert "error" in api.add_word(bad)
    assert "error" in api.add_fix("sea whiz", "")
    assert api.dictionary()["words"] == ["Ghostwriter"]


@pytest.mark.parametrize(("git", "latest", "status"), [
    (True, None, "git"),
    (False, OSError("offline"), "error"),
    (False, "0.0.1", "current"),
    (False, "99.0.0", "available"),
])
def test_check_for_updates_reports_each_outcome(api, monkeypatch, git, latest, status):
    monkeypatch.setattr(updates, "is_git_checkout", lambda: git)

    def latest_version():
        if isinstance(latest, Exception):
            raise latest
        return latest

    monkeypatch.setattr(updates, "latest_version", latest_version)
    assert api.check_for_updates()["status"] == status


def test_history_calls_search_and_clear(api, tmp_path):
    history = History(tmp_path / "history.db")
    history.add("Deploy the MySQL backup", "Windows Terminal", 3.0)
    history.add("See you Friday", "Discord", 1.0)
    assert api.history("mysql")["total"] == 1
    result = api.history(app="Discord")
    assert [item["text"] for item in result["items"]] == ["See you Friday"]
    assert set(result["apps"]) == {"Windows Terminal", "Discord"}
    assert api.history_summary()["dictations_today"] == 2
    stamp = api.history_stamp()
    api.clear_history()
    assert api.history()["total"] == 0 and api.history_stamp() != stamp


def _open_page(api, drive, tmp_path):
    """Open the real page in a window and run drive(run) against it (page clicks only, no real typing)."""
    import webview

    view = webview.create_window(window.TITLE, url=str(UI_DIR / "index.html"), js_api=api, width=window.WIDTH,
                                 height=window.HEIGHT, frameless=True, easy_drag=False, background_color="#121316")
    api.attach(view)

    def run(script: str, wait: float = 0.4):
        value = view.evaluate_js(script)
        time.sleep(wait)
        return value

    def start():
        try:
            for _ in range(60):
                if view.evaluate_js("typeof state !== 'undefined' && state !== null"):
                    break
                time.sleep(0.25)
            time.sleep(0.5)  # the first history check
            drive(run)
        finally:
            view.destroy()

    webview.start(start, http_server=True, private_mode=True, storage_path=str(tmp_path / "webview"),
                  icon=str(ICON_PATH))


def test_the_page_changes_settings_and_the_dictionary(api, tmp_path):
    results = {}

    def drive(run):
        run("document.querySelector('#hotkeys input[value=\"Right Ctrl\"]').click()")
        run("document.querySelector('#settings .switch[data-setting=hands_free]').click()")
        results["minutes_locked"] = run("document.getElementById('hands-free-minutes').disabled")
        run("document.querySelector('#settings .switch[data-setting=hands_free]').click()")
        run("const m = document.getElementById('hands-free-minutes'); m.value = '30'; m.dispatchEvent(new Event('change'))")
        run("document.querySelector('#themes input[value=light]').click()")
        results["theme"] = run("document.getElementById('app').dataset.theme")
        results["hint"] = run("document.getElementById('tryit').placeholder")
        run("document.getElementById('new-word').value = 'Brightwater'; document.getElementById('add-word').requestSubmit()")
        run("document.getElementById('new-heard').value = 'my sequel'; document.getElementById('new-write').value = 'MySQL'; "
            "document.getElementById('add-fix').requestSubmit()")
        run("document.getElementById('new-word').value = 'a -> b'; document.getElementById('add-word').requestSubmit()")
        results["error"] = run("document.getElementById('word-error').textContent")
        run("document.querySelector('#word-list .remove[aria-label=\"Remove Ghostwriter\"]').click()")
        results["chips"] = run("[...document.querySelectorAll('#word-list li')].map((li) => li.textContent).join('|')")

    _open_page(api, drive, tmp_path)

    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["hotkey"] == "Right Ctrl"
    assert saved["hands_free"] is True and results["minutes_locked"] is True
    assert saved["hands_free_minutes"] == 30
    assert saved["theme"] == "light" and results["theme"] == "light"
    assert "hold Right Ctrl" in results["hint"]
    assert "->" in results["error"]
    assert results["chips"] == "Brightwater"
    dictionary = (tmp_path / "dictionary.txt").read_text(encoding="utf-8")
    assert "my sequel -> MySQL" in dictionary and "Ghostwriter" not in dictionary.replace("# notes", "")


def test_home_and_the_history_page_show_dictations(api, tmp_path):
    history = History(tmp_path / "history.db")
    history.add("Book the ceramic coating for Friday.", "Google Chrome", 4.2, at=datetime.now() - timedelta(days=1))
    history.add("gg, queue up again in five", "Discord", 3.0)
    history.add("Deploy the MySQL backup tonight", "Windows Terminal", 6.5)
    texts = "[...document.querySelectorAll('{} .entry-text')].map((node) => node.textContent)"
    results = {}

    def drive(run):
        results["today"] = run("[document.getElementById('words-today').textContent, document.getElementById('dictations-today').textContent]")
        results["recent"] = run(texts.format("#recent-list"))
        run("document.querySelector('.nav[data-view=history]').click()")
        results["days"] = run("[...document.querySelectorAll('#history-days .day')].map((node) => node.textContent)")
        results["filters"] = run("[...document.querySelectorAll('#history-filters label')].map((node) => node.textContent)")
        run("const s = document.getElementById('history-search'); s.value = 'mysql'; s.dispatchEvent(new Event('input'))", wait=0.8)
        results["search"] = run(texts.format("#history-days"))
        run("const s = document.getElementById('history-search'); s.value = ''; s.dispatchEvent(new Event('input'))", wait=0.8)
        run("document.querySelector('#history-filters input[value=Discord]').click()")
        results["filtered"] = run(texts.format("#history-days"))
        run("document.querySelector('#history-filters input[value=\"\"]').click()")
        history.add("This one arrives while the window is open.", "Notepad", 2.0)
        time.sleep(1.5)
        results["live"] = run(texts.format("#history-days"))
        run("document.getElementById('clear-history').click()")
        results["question"] = run("document.getElementById('clear-question').textContent")
        run("document.getElementById('clear-yes').click()", wait=1.5)
        results["cleared"] = run("[document.getElementById('history-empty').hidden, document.querySelectorAll('.entry').length]")

    _open_page(api, drive, tmp_path)

    assert results["today"] == ["11", "2"]
    assert results["recent"] == ["Deploy the MySQL backup tonight", "gg, queue up again in five",
                                 "Book the ceramic coating for Friday."]
    assert results["days"] == ["Today", "Yesterday"]
    assert results["filters"] == ["All", "Windows Terminal", "Discord", "Google Chrome"]  # ties go to the latest
    assert results["search"] == ["Deploy the MySQL backup tonight"]
    assert results["filtered"] == ["gg, queue up again in five"]
    assert results["live"][0] == "This one arrives while the window is open." and len(results["live"]) == 4
    assert results["question"] == "Delete all 4 dictations?"
    assert results["cleared"] == [False, 0]
    assert history.search()["total"] == 0


def test_a_new_install_opens_on_the_welcome(tmp_path):
    startup_path = tmp_path / "startup.json"
    startup.write(startup_path, model="downloading", done=400_000_000, total=1_600_000_000)
    api = Api(settings_path=tmp_path / "settings.json", dictionary_path=tmp_path / "dictionary.txt",
              history_path=tmp_path / "history.db", startup_path=startup_path)
    results = {}

    def drive(run):
        results["welcome"] = run("[app.classList.contains('in-setup'), document.getElementById('window-title').textContent]")
        results["downloading"] = run("[document.getElementById('download-amount').textContent, "
                                     "document.getElementById('setup-next').disabled]")
        startup.write(startup_path, model="ready")
        time.sleep(1)
        results["ready"] = run("[document.getElementById('download-title').textContent, "
                               "document.getElementById('setup-next').disabled]")
        run("document.getElementById('setup-next').click()")
        run("document.querySelector('#setup-hotkeys input[value=\"Caps Lock\"]').click()")
        run("document.getElementById('setup-next').click()")
        results["try"] = run("[document.getElementById('setup-next').textContent, "
                             "document.querySelector('[data-step=\"3\"] kbd').textContent]")
        run("document.getElementById('setup-next').click()")
        results["finished"] = run("[app.classList.contains('in-setup'), document.getElementById('home').hidden]")

    _open_page(api, drive, tmp_path)

    assert results["welcome"] == [True, "Ghostwriter setup"]
    assert results["downloading"] == ["0.4 of 1.6 GB", True]  # can't continue until the model is ready
    assert results["ready"] == ["Ready to go", False]
    assert results["try"] == ["Finish", "Caps Lock"]
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["hotkey"] == "Caps Lock"
    assert results["finished"] == [False, False]


def _wait_for(check, timeout: float = 20.0) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if check():
            return True
        time.sleep(0.25)
    return False


def test_opening_twice_gives_one_window_and_quitting_closes_it():
    if window._app_windows():
        pytest.skip("Ghostwriter's window is open, and this test would close it")
    window.open_window()
    assert _wait_for(lambda: len(window._app_windows()) == 1), "the window never opened"
    window.open_window()
    time.sleep(3)  # long enough for a second copy to start, see the first, and step aside
    assert len(window._app_windows()) == 1
    window.close_window()
    assert _wait_for(lambda: not window._app_windows(), timeout=10), "the window didn't close"
