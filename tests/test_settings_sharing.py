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
    real_read_text = Path.read_text
    reads = []

    def caught_halfway(self, *args, **kwargs):
        reads.append(self)
        return '{"hotkey": "Ca' if len(reads) == 1 else real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", caught_halfway)
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
    assert tray.reload_if_changed()  # the window's change still reaches the running app
    assert tray.pill is False
    assert not tray.reload_if_changed()


def test_a_change_with_nothing_new_on_disk_isnt_news(tmp_path):
    path = tmp_path / "settings.json"
    running = Settings.load(path)
    running.change("sounds", False)
    assert not running.reload_if_changed()
    assert Settings.load(path).sounds is False
