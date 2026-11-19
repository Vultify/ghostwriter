"""The app window on Linux: it starts as its own program, floats on Hyprland at a size that fits the screen, can be
found to close or focus, and its page gets what it needs to look right on Linux."""

import json
import subprocess
import sys
import time

from ghostwriter.linux import app_window, desktop, shortcuts
from ghostwriter.window import TITLE, Api


def _api(folder):
    return Api(settings_path=folder / "settings.json", dictionary_path=folder / "dictionary.txt",
               history_path=folder / "history.db", startup_path=folder / "startup.json",
               login_folder=folder / "autostart")


def test_the_page_lets_the_desktop_draw_the_frame_and_names_the_system(tmp_path):
    state = _api(tmp_path).state()
    assert state["ownFrame"] is False
    assert state["system"] == desktop.NAME and state["appMenu"] == desktop.APP_MENU


def test_the_start_at_login_switch_adds_and_removes_the_autostart_entry(tmp_path):
    api = _api(tmp_path)
    assert api.state()["startAtLogin"] is False
    api.set_start_at_login(True)
    assert api.state()["startAtLogin"] is True and (tmp_path / "autostart" / shortcuts.ENTRY_NAME).exists()
    api.set_start_at_login(False)
    assert api.state()["startAtLogin"] is False


def test_the_window_starts_as_its_own_program(monkeypatch):
    started = []
    monkeypatch.setattr(app_window.hyprland, "running", lambda: False)
    monkeypatch.setattr(app_window.subprocess, "Popen", lambda args, **options: started.append((args, options)))
    app_window.open_window()
    args, options = started[0]
    assert args == [sys.executable, "-m", "ghostwriter.window"]
    assert options["cwd"] == app_window.PROJECT and options["start_new_session"]


def test_on_hyprland_it_floats_centered_and_shrinks_to_fit_a_small_screen(monkeypatch):
    sent = []
    screen = {"focused": True, "width": 1366, "height": 768, "scale": 1, "reserved": [0, 24, 0, 0]}

    def request(command):
        sent.append(command)
        return json.dumps([screen]) if command == "j/monitors" else "ok"

    monkeypatch.setattr(app_window.hyprland, "request", request)
    app_window._float_on_hyprland()
    rule = sent[-1]
    assert rule.startswith("eval ") and "float = true, center = true" in rule
    assert "size = { 1286, 664 }" in rule  # the width and height that fit inside the margins and under the bar
    assert '"^io\\\\.github\\\\.vultify\\\\.Ghostwriter$"' in rule
    assert 'title = "^Ghostwriter$"' in rule  # only the main window
    assert 'title = "^(Open|Save) file$" },\n  float = true, center = true, size = { 875, 600 }' in rule  # its dialogs
    assert "set_enabled(false)" in rule  # replaces the last launch's rule instead of piling up


def test_on_a_tiny_screen_it_never_goes_below_the_size_the_page_needs(monkeypatch):
    sent = []
    screen = {"focused": True, "width": 960, "height": 600, "scale": 1, "reserved": [0, 26, 0, 0]}
    monkeypatch.setattr(app_window.hyprland, "request",
                        lambda command: sent.append(command) or (json.dumps([screen]) if command == "j/monitors" else "ok"))
    app_window._float_on_hyprland()
    assert f"size = {{ {app_window.MIN_WIDTH}, {app_window.MIN_HEIGHT} }}" in sent[-1]
    assert "size = { 875, 494 }" in sent[-1]  # the file dialogs, shrunk to fit too


def test_the_float_rule_matches_the_windows_own_title():
    assert app_window.TITLE == TITLE


def test_opening_again_leaves_the_open_windows_rule_alone(monkeypatch):
    floated = []
    monkeypatch.setattr(app_window.hyprland, "running", lambda: True)
    monkeypatch.setattr(app_window, "_float_on_hyprland", lambda: floated.append(True))
    monkeypatch.setattr(app_window.subprocess, "Popen", lambda args, **options: None)
    monkeypatch.setattr(app_window, "_window_processes", lambda: [4242])
    app_window.open_window()
    assert not floated
    monkeypatch.setattr(app_window, "_window_processes", lambda: [])
    app_window.open_window()
    assert floated


def test_closing_finds_the_window_by_its_command_and_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(app_window, "PROJECT", tmp_path)  # so a real open window is never touched
    stand_in = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "-m", "ghostwriter.window"],
                                cwd=tmp_path)
    elsewhere = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "-m", "ghostwriter.window"])
    try:
        time.sleep(0.3)
        assert app_window._window_processes() == [stand_in.pid]
        app_window.close_window("Ghostwriter")
        assert stand_in.wait(timeout=5) is not None
        assert elsewhere.poll() is None  # another install's window stays open
    finally:
        for process in (stand_in, elsewhere):
            process.kill()
            process.wait()
