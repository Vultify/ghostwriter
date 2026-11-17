"""Ghostwriter's launcher entry and start at login on Linux: standard desktop entries that launchers, autostart, and
systemd read the way they were meant."""

import shutil
import subprocess
import sys
import time

import pytest

if sys.platform != "linux":  # skipped here rather than in conftest, so a Linux-only change stays out of shared files
    pytest.skip("Linux only", allow_module_level=True)

from gi.repository import GioUnix  # noqa: E402
from PIL import Image  # noqa: E402

from ghostwriter.linux import shortcuts  # noqa: E402
from ghostwriter.paths import PROJECT  # noqa: E402


@pytest.fixture
def project(monkeypatch, tmp_path):
    """A stand-in project folder whose path has spaces, quotes, and a dollar sign in it. Its Python only notes the
    folder it was started in and the arguments it got."""
    folder = tmp_path / "Bob's \"Apps\" $HOME"
    python = folder / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$PWD\" \"$@\" > '{tmp_path}/started'\n")
    python.chmod(0o755)
    monkeypatch.setattr(shortcuts, "PROJECT", folder)
    monkeypatch.setattr(shortcuts, "PYTHON", python)
    return folder


def _launch(entry):
    """Start an entry the way a desktop does, and return the folder and arguments its program got."""
    record = entry.parents[1] / "started"
    record.unlink(missing_ok=True)
    assert GioUnix.DesktopAppInfo.new_from_filename(str(entry)).launch([], None)
    for _ in range(100):
        if record.exists() and record.read_text().endswith("\n"):
            break
        time.sleep(0.02)
    folder, *arguments = record.read_text().splitlines()
    return folder, arguments


def test_the_launcher_entry_starts_ghostwriter_from_its_folder_with_its_icon(project, tmp_path):
    entry = shortcuts.make_launcher_entry(tmp_path / "applications", tmp_path / "icons")
    assert entry.name == "io.github.vultify.Ghostwriter.desktop"  # named for the window's app id, so they match
    assert _launch(entry) == (str(project), ["-m", "ghostwriter"])
    assert "NoDisplay" not in entry.read_text()
    for size in shortcuts.ICON_SIZES:
        with Image.open(tmp_path / "icons" / f"{size}x{size}" / "apps" / "io.github.vultify.Ghostwriter.png") as icon:
            assert icon.size == (size, size)


def test_an_icon_size_missing_from_the_ico_is_scaled_to_fit(monkeypatch, tmp_path):
    monkeypatch.setattr(shortcuts, "ICON_SIZES", (20,))
    shortcuts.make_launcher_entry(tmp_path / "applications", tmp_path / "icons")
    with Image.open(tmp_path / "icons" / "20x20" / "apps" / "io.github.vultify.Ghostwriter.png") as icon:
        assert icon.size == (20, 20)


@pytest.mark.skipif(not shutil.which("desktop-file-validate"), reason="desktop-file-utils isn't installed")
def test_both_entries_pass_the_desktop_entry_checker(tmp_path):
    entry = shortcuts.make_launcher_entry(tmp_path / "applications", tmp_path / "icons")
    shortcuts.set_start_at_login(True, tmp_path / "autostart")
    checked = subprocess.run(["desktop-file-validate", str(entry), str(tmp_path / "autostart" / entry.name)],
                             capture_output=True, text=True)
    assert checked.returncode == 0 and not checked.stdout, checked.stdout


def test_start_at_login_is_an_entry_in_the_autostart_folder(project, tmp_path):
    folder = tmp_path / "autostart"
    assert not shortcuts.starts_at_login(folder)
    shortcuts.set_start_at_login(True, folder)
    assert shortcuts.starts_at_login(folder)
    assert _launch(folder / shortcuts.ENTRY_NAME) == (str(project), ["-m", "ghostwriter", "--tray"])
    assert not list(folder.glob("*.new"))
    shortcuts.set_start_at_login(False, folder)
    assert not shortcuts.starts_at_login(folder)
    shortcuts.set_start_at_login(False, folder)  # already off is fine


@pytest.mark.parametrize("off_switch", ["Hidden=true", "X-GNOME-Autostart-enabled=false"])
def test_start_at_login_reads_off_when_the_desktops_own_settings_turned_it_off(tmp_path, off_switch):
    """GNOME Tweaks and KDE's autostart settings keep the entry and switch it off inside."""
    folder = tmp_path / "autostart"
    shortcuts.set_start_at_login(True, folder)
    entry = folder / shortcuts.ENTRY_NAME
    entry.write_text(entry.read_text() + off_switch + "\n")
    assert not shortcuts.starts_at_login(folder)
    shortcuts.set_start_at_login(True, folder)
    assert shortcuts.starts_at_login(folder)


def test_another_copys_entry_is_not_this_copys_setting(tmp_path):
    """Two copies, like an installed one and a workshop checkout, share the entry's name."""
    folder = tmp_path / "autostart"
    folder.mkdir()
    (folder / shortcuts.ENTRY_NAME).write_text("[Desktop Entry]\nType=Application\nName=Ghostwriter\n"
                                               "Exec=/elsewhere/.venv/bin/python -m ghostwriter --tray\n"
                                               "Path=/elsewhere\n")
    assert not shortcuts.starts_at_login(folder)


GENERATOR = "/usr/lib/systemd/user-generators/systemd-xdg-autostart-generator"


@pytest.mark.skipif(not shutil.which(GENERATOR), reason="no systemd autostart")
def test_systemd_starts_it_at_login_in_the_tray_from_the_project_folder(monkeypatch, tmp_path):
    """Omarchy (through uwsm) and GNOME turn autostart entries into systemd services."""
    folder = tmp_path / "ghostwriter"
    monkeypatch.setattr(shortcuts, "PROJECT", folder)
    python = folder / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("")
    python.chmod(0o755)  # systemd skips entries whose program isn't there
    monkeypatch.setattr(shortcuts, "PYTHON", python)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CONFIG_DIRS", str(tmp_path / "none"))
    shortcuts.set_start_at_login(True)
    subprocess.run([GENERATOR, tmp_path, tmp_path, tmp_path], check=True)
    service = (tmp_path / "app-io.github.vultify.Ghostwriter@autostart.service").read_text()
    assert f"ExecStart=:{folder}/.venv/bin/python -m ghostwriter --tray\n" in service
    assert f"WorkingDirectory=-{folder}\n" in service


def _run_module(tmp_path):
    folders = {"XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CONFIG_HOME": str(tmp_path / "config")}
    subprocess.run([sys.executable, "-m", "ghostwriter.linux.shortcuts"], cwd=PROJECT, check=True,
                   env={"HOME": str(tmp_path), "PATH": "/usr/bin", **folders}, capture_output=True)


def test_running_it_adds_the_launcher_entry_and_refreshes_this_copys_start_at_login(tmp_path):
    login_entry = tmp_path / "config" / "autostart" / shortcuts.ENTRY_NAME
    login_entry.parent.mkdir(parents=True)
    login_entry.write_text(f"[Desktop Entry]\nExec=/old/python -m ghostwriter --tray\nPath={PROJECT}\n")
    _run_module(tmp_path)
    assert (tmp_path / "data" / "applications" / shortcuts.ENTRY_NAME).exists()
    assert "/old/python" not in login_entry.read_text()


def test_running_it_leaves_another_copys_start_at_login_alone(tmp_path):
    login_entry = tmp_path / "config" / "autostart" / shortcuts.ENTRY_NAME
    login_entry.parent.mkdir(parents=True)
    other = "[Desktop Entry]\nExec=/elsewhere/python -m ghostwriter --tray\nPath=/elsewhere\n"
    login_entry.write_text(other)
    _run_module(tmp_path)
    assert login_entry.read_text() == other
