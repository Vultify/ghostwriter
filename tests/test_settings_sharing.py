"""settings.json is shared by the tray app, the app window, and Omarchy's panel: a read in the middle of another
program's save never turns into defaults, and a save never undoes a change another program just made."""

import json
import os
from pathlib import Path

from ghostwriter import settings as settings_module
from ghostwriter.settings import Settings


def _save_elsewhere(path: Path, text: str) -> None:
    """Write the file the way another program would, and make sure its clock shows the change."""
    path.write_text(text, encoding="utf-8")
    later = path.stat().st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(later, later))


def test_a_read_in_the_middle_of_a_save_waits_for_the_whole_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"hotkey": "Caps Lock", "pill": False}), encoding="utf-8")
    real_read_bytes = Path.read_bytes
    reads = []

    def caught_halfway(self):
        reads.append(self)
        return b'{"hotkey": "Ca' if len(reads) == 1 else real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", caught_halfway)
    loaded = Settings.load(path)
    assert (loaded.hotkey, loaded.pill) == ("Caps Lock", False)
    assert len(reads) == 2


def test_the_running_app_keeps_its_settings_while_the_file_is_unreadable(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "_READ_TRIES", 2)
    path = tmp_path / "settings.json"
    running = Settings.load(path)
    running.change("hotkey", "Caps Lock")
    running.change("sounds", False)
    _save_elsewhere(path, '{"hotkey": "Ca')  # a save that never finished
    assert not running.reload_if_changed()
    assert (running.hotkey, running.sounds) == ("Caps Lock", False)
    _save_elsewhere(path, json.dumps({**running.saved(), "pill": False}))  # the next good save still lands
    assert running.reload_if_changed() and running.pill is False


def test_a_change_keeps_what_another_program_saved_a_moment_ago(tmp_path):
    path = tmp_path / "settings.json"
    tray = Settings.load(path)
    tray.save()
    Settings.load(path).change("pill", False)  # the app window, before the tray's next look at the file
    tray.change("sounds", False)  # the tray menu, still holding the old pill setting
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert (saved["pill"], saved["sounds"]) == (False, False)
    assert tray.pill is False  # the window's change reached the running app with the tray's own save
    assert not tray.reload_if_changed()


def test_a_change_with_nothing_new_on_disk_isnt_news(tmp_path):
    path = tmp_path / "settings.json"
    running = Settings.load(path)
    running.change("sounds", False)
    assert not running.reload_if_changed()
    assert Settings.load(path).sounds is False


def test_a_save_in_the_same_clock_tick_still_reaches_the_running_app(tmp_path):
    path = tmp_path / "settings.json"
    tray = Settings.load(path)
    tray.save()
    stamp = path.stat().st_mtime_ns
    Settings.load(path).change("pill", False)  # the app window, in the same tick as the tray's save
    os.utime(path, ns=(stamp, stamp))
    assert tray.reload_if_changed()
    assert tray.pill is False and not tray.reload_if_changed()


def test_a_change_takes_in_what_another_program_saved_right_away(tmp_path):
    path = tmp_path / "settings.json"
    tray = Settings.load(path)
    tray.save()
    Settings.load(path).change("pill", False)
    tray.change("sounds", False)
    assert (tray.pill, tray.sounds) == (False, False)  # the menu and apply_settings see both at once


def test_a_broken_file_is_warned_about_once_and_read_again_when_it_changes(tmp_path, caplog):
    path = tmp_path / "settings.json"
    tray = Settings.load(path)
    tray.save()
    path.write_text("{ not json", encoding="utf-8")
    assert not tray.reload_if_changed() and not tray.reload_if_changed()
    assert caplog.text.count("Ignoring unreadable") == 1
    Settings(path=path, pill=False).save()
    assert tray.reload_if_changed() and tray.pill is False


def test_a_file_that_was_unreadable_for_a_moment_is_read_again_in_the_same_tick(tmp_path):
    path = tmp_path / "settings.json"
    tray = Settings.load(path)
    tray.save()
    path.write_text("{ half saved", encoding="utf-8")
    stamp = path.stat().st_mtime_ns
    assert not tray.reload_if_changed()
    Settings(path=path, pill=False).save()  # the rest of the save lands in the same clock tick
    os.utime(path, ns=(stamp, stamp))
    assert tray.reload_if_changed() and tray.pill is False


def test_a_change_never_writes_defaults_over_a_file_it_cant_read(tmp_path):
    path = tmp_path / "settings.json"
    Settings(path=path, hotkey="Right Ctrl", pill=False).save()
    good = path.read_text(encoding="utf-8")
    path.write_text(good[: len(good) // 2], encoding="utf-8")  # left half saved
    window = Settings.load(path)
    window.change("theme", "light")
    assert path.read_text(encoding="utf-8") == good[: len(good) // 2]  # nothing written over it


def test_a_settings_file_that_stays_broken_is_repaired_from_the_settings_in_use(tmp_path):
    path = tmp_path / "settings.json"
    tray = Settings.load(path)
    tray.change("hotkey", "Caps Lock")
    path.write_text("{ broken for good", encoding="utf-8")
    assert not tray.reload_if_changed()  # might still be a save going on
    assert not Settings.load(path).change("pill", False)  # the window waits for the repair
    assert not tray.reload_if_changed()  # the same broken file a check later: repaired
    assert json.loads(path.read_text(encoding="utf-8"))["hotkey"] == "Caps Lock"
    assert (tmp_path / "settings.json.broken").read_text(encoding="utf-8") == "{ broken for good"
    assert Settings.load(path).change("pill", False)
