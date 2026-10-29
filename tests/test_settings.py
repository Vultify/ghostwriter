"""Settings load and save safely, the tray menu changes them, and the app applies the changes live."""

import json
import os
import time

from conftest import press_key
from test_status import FakePaster, FakeRecorder, FakeTranscriber

from ghostwriter import app, sounds, win32
from ghostwriter.app import Dictation, StatusDisplay, claim_single_instance
from ghostwriter.recorder import Recorder, list_microphones
from ghostwriter.settings import Settings, default_hotkey, keyboard_uses_altgr
from ghostwriter.state import State
from ghostwriter.tray import Tray


def test_missing_file_means_defaults(tmp_path):
    settings = Settings.load(tmp_path / "settings.json")
    assert (settings.hotkey, settings.microphone, settings.sounds) == (default_hotkey(), None, True)


def test_the_default_hotkey_avoids_altgr_keyboards():
    # This PC has a plain US layout, so Right Alt is free; a layout with AltGr would get Right Ctrl.
    assert keyboard_uses_altgr() is False
    assert default_hotkey() == "Right Alt"


def test_settings_survive_a_save_and_load(tmp_path):
    path = tmp_path / "settings.json"
    Settings(hotkey="Caps Lock", microphone="Mic A", sounds=False, path=path).save()
    loaded = Settings.load(path)
    assert (loaded.hotkey, loaded.microphone, loaded.sounds) == ("Caps Lock", "Mic A", False)


def test_a_broken_or_odd_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert Settings.load(path).hotkey == default_hotkey()
    path.write_text(json.dumps({"hotkey": "Banana", "sounds": "loud"}), encoding="utf-8")
    loaded = Settings.load(path)
    assert (loaded.hotkey, loaded.sounds) == (default_hotkey(), True)


def test_tray_menu_changes_are_saved_and_reported(tmp_path):
    settings = Settings.load(tmp_path / "settings.json")
    tray = Tray(settings, ["Mic A"], on_quit=lambda: None, files={})
    changes = []
    tray.on_change = lambda: changes.append(settings.hotkey)
    tray._change(hotkey="Right Ctrl")
    tray._change(sounds=False)
    saved = json.loads(settings.path.read_text(encoding="utf-8"))
    assert saved == {"hotkey": "Right Ctrl", "microphone": None, "sounds": False,
                     "hands_free": True, "hands_free_minutes": 15, "theme": "system", "history": True}
    assert changes == ["Right Ctrl", "Right Ctrl"]
    tray.set_state(State.READY)
    assert "Right Ctrl" in tray._tray.title


def test_switching_the_hotkey_takes_effect_right_away():
    states: list[State] = []
    dictation = Dictation(FakeTranscriber(), FakeRecorder(), FakePaster(), allow_injected=True, on_state=states.append)
    dictation.start()
    try:
        dictation.set_hotkey(win32.VK_RCONTROL)
        press_key(win32.VK_RCONTROL)
        time.sleep(0.5)
        press_key(win32.VK_RCONTROL, release=True)
        deadline = time.perf_counter() + 3
        while time.perf_counter() < deadline and states[-1:] != [State.READY]:
            time.sleep(0.02)
    finally:
        dictation.stop()
    assert states == [State.LISTENING, State.WORKING, State.READY]


def test_turning_sounds_off_silences_them(monkeypatch):
    played = []
    monkeypatch.setattr(sounds, "play_start", lambda: played.append("start"))
    monkeypatch.setattr(sounds, "play_stop", lambda: played.append("stop"))

    class Quiet:
        def set_state(self, state):
            pass

        def show(self, mode):
            pass

    settings = Settings()
    display = StatusDisplay(Quiet(), Quiet(), settings)
    display(State.LISTENING)
    display(State.READY)
    settings.sounds = False
    display(State.LISTENING)
    display(State.READY)
    assert played == ["start", "stop"]


def test_a_chosen_mic_records_and_an_unplugged_one_falls_back_to_default():
    for microphone in (list_microphones()[0], "A mic that isn't plugged in"):
        recorder = Recorder(microphone=microphone)
        recorder.start()
        time.sleep(0.2)
        assert len(recorder.stop()) > 0


def test_only_one_copy_can_run_at_a_time():
    name = f"Local\\GhostwriterTest{time.time_ns()}"
    assert claim_single_instance(name)
    assert not claim_single_instance(name)
    assert app.LOG_PATH.name == "ghostwriter.log"


def test_new_settings_load_with_safe_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"hands_free": "yes", "hands_free_minutes": 7, "theme": "blue"}), encoding="utf-8")
    loaded = Settings.load(path)
    assert (loaded.hands_free, loaded.hands_free_minutes, loaded.theme) == (True, 15, "system")


def test_the_running_app_picks_up_what_the_window_saves(tmp_path):
    path = tmp_path / "settings.json"
    running = Settings.load(path)
    running.save()
    assert not running.reload_if_changed()  # its own save isn't news
    Settings.load(path).change("hands_free", False)
    later = path.stat().st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(later, later))  # make sure the change is seen even on a coarse file clock
    assert running.reload_if_changed()
    assert running.hands_free is False
    assert not running.reload_if_changed()
