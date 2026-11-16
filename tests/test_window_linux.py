"""The app window on Linux: it starts as its own program, floats on Hyprland at a size that fits the screen, can be
found to close or focus, and its page gets what it needs to look right on Linux."""

import json
import subprocess
import sys
import time

from ghostwriter.linux import app_window, desktop, shortcuts
from ghostwriter.window import Api


def test_the_page_lets_the_desktop_draw_the_frame_and_names_the_system(tmp_path):
    state = Api(settings_path=tmp_path / "settings.json", dictionary_path=tmp_path / "dictionary.txt",
                history_path=tmp_path / "history.db", startup_path=tmp_path / "startup.json").state()
    assert state["ownFrame"] is False
    assert state["system"] == desktop.NAME and state["appMenu"] == desktop.APP_MENU
    assert state["startAtLogin"] is False


def test_start_at_login_stays_off_without_an_error_until_linux_has_it():
    shortcuts.set_start_at_login(True)
    assert not shortcuts.starts_at_login()


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
    assert "size = { 1120, 664 }" in rule  # full width, and the height that fits under the bar
    assert '"^io\\\\.github\\\\.vultify\\\\.Ghostwriter$"' in rule
    assert "set_enabled(false)" in rule  # replaces the last launch's rule instead of piling up


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
