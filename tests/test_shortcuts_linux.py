"""Ghostwriter's launcher entry and start at login on Linux: standard desktop entries that launchers, autostart, and
systemd read the way they were meant."""

import shutil
import subprocess
import sys

import pytest

if sys.platform != "linux":  # skipped here rather than in conftest, so a Linux-only change stays out of shared files
    pytest.skip("Linux only", allow_module_level=True)

from gi.repository import GioUnix, GLib  # noqa: E402
from PIL import Image  # noqa: E402

from ghostwriter.linux import shortcuts  # noqa: E402
from ghostwriter.paths import PROJECT  # noqa: E402


@pytest.fixture
def odd_project(monkeypatch, tmp_path):
    """A project folder whose path has spaces, quotes, and a dollar sign in it."""
    folder = tmp_path / "Bob's \"Apps\" $HOME"
    python = folder / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("")
    python.chmod(0o755)  # desktops skip entries whose program isn't there
    monkeypatch.setattr(shortcuts, "PROJECT", folder)
    monkeypatch.setattr(shortcuts, "PYTHON", python)
    return folder


def _command(entry):
    info = GioUnix.DesktopAppInfo.new_from_filename(str(entry))
    return GLib.shell_parse_argv(info.get_commandline())[1], info.get_string("Path")


def test_the_launcher_entry_starts_ghostwriter_from_its_folder_with_its_icon(odd_project, tmp_path):
    entry = shortcuts.make_launcher_entry(tmp_path / "applications", tmp_path / "icons")
    assert entry.name == "io.github.vultify.Ghostwriter.desktop"  # named for the window's app id, so they match
    assert _command(entry) == ([str(odd_project / ".venv/bin/python"), "-m", "ghostwriter"], str(odd_project))
    assert "NoDisplay" not in entry.read_text()
    for size in shortcuts.ICON_SIZES:
        with Image.open(tmp_path / "icons" / f"{size}x{size}" / "apps" / "io.github.vultify.Ghostwriter.png") as icon:
            assert icon.size == (size, size)


@pytest.mark.skipif(not shutil.which("desktop-file-validate"), reason="desktop-file-utils isn't installed")
def test_both_entries_pass_the_desktop_entry_checker(tmp_path):
    entry = shortcuts.make_launcher_entry(tmp_path / "applications", tmp_path / "icons")
    shortcuts.set_start_at_login(True, tmp_path / "autostart")
    checked = subprocess.run(["desktop-file-validate", str(entry), str(tmp_path / "autostart" / entry.name)],
                             capture_output=True, text=True)
    assert checked.returncode == 0 and not checked.stdout, checked.stdout


def test_start_at_login_is_an_entry_in_the_autostart_folder(odd_project, tmp_path):
    folder = tmp_path / "autostart"
    assert not shortcuts.starts_at_login(folder)
    shortcuts.set_start_at_login(True, folder)
    assert shortcuts.starts_at_login(folder)
    assert _command(folder / shortcuts.ENTRY_NAME) == (
        [str(odd_project / ".venv/bin/python"), "-m", "ghostwriter", "--tray"], str(odd_project))
    shortcuts.set_start_at_login(False, folder)
    assert not shortcuts.starts_at_login(folder)
    shortcuts.set_start_at_login(False, folder)  # already off is fine


GENERATOR = "/usr/lib/systemd/user-generators/systemd-xdg-autostart-generator"


@pytest.mark.skipif(not shutil.which(GENERATOR), reason="no systemd autostart")
def test_systemd_starts_it_at_login_in_the_tray_from_the_project_folder(monkeypatch, tmp_path):
    """Omarchy (through uwsm) and GNOME turn autostart entries into systemd services."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CONFIG_DIRS", str(tmp_path / "none"))
    shortcuts.set_start_at_login(True)
    subprocess.run([GENERATOR, tmp_path, tmp_path, tmp_path], check=True)
    service = (tmp_path / "app-io.github.vultify.Ghostwriter@autostart.service").read_text()
    assert f"ExecStart=:{PROJECT}/.venv/bin/python -m ghostwriter --tray\n" in service
    assert f"WorkingDirectory=-{PROJECT}\n" in service


def test_running_it_adds_the_launcher_entry_and_refreshes_start_at_login(tmp_path):
    folders = {"XDG_DATA_HOME": str(tmp_path / "data"), "XDG_CONFIG_HOME": str(tmp_path / "config")}
    login_entry = tmp_path / "config" / "autostart" / shortcuts.ENTRY_NAME
    login_entry.parent.mkdir(parents=True)
    login_entry.write_text("[Desktop Entry]\nExec=/old/place/python -m ghostwriter --tray\n")
    subprocess.run([sys.executable, "-m", "ghostwriter.linux.shortcuts"], cwd=PROJECT, check=True,
                   env={"HOME": str(tmp_path), "PATH": "/usr/bin", **folders}, capture_output=True)
    assert (tmp_path / "data" / "applications" / shortcuts.ENTRY_NAME).exists()
    assert "/old/place" not in login_entry.read_text()
