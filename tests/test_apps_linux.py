"""Naming the app in front on Linux, from launcher entries (.desktop files) in stand-in data folders."""

from pathlib import Path

import pytest

from ghostwriter.linux import desktop_files
from ghostwriter.linux.paster import App, app_name
from ghostwriter.paths import PROJECT

ENTRIES = {
    "home/applications/WhatsApp.desktop":
        "[Desktop Entry]\nName=WhatsApp\nExec=omarchy-launch-webapp https://web.whatsapp.com/\n",
    "home/applications/chromium.desktop": "[Desktop Entry]\nName=My Chromium\nExec=chromium --ozone-platform=wayland\n",
    "shared/applications/chromium.desktop":
        "[Desktop Entry]\nName=Chromium\nExec=/usr/bin/chromium %U\n\n[Desktop Action new-window]\nName=New Window\n",
    "shared/applications/org.gnome.Nautilus.desktop": "[Desktop Entry]\nName=Files\nName[de]=Dateien\nExec=nautilus\n",
    "shared/applications/code.desktop": "[Desktop Entry]\nName=Visual Studio Code\nExec=code\nStartupWMClass=Code\n",
    "shared/applications/broken.desktop": "Name=No section, so not an entry\n",
}


@pytest.fixture(autouse=True)
def launcher_entries(tmp_path, monkeypatch):
    for relative, text in ENTRIES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "shared"))
    desktop_files.installed.cache_clear()
    app_name.cache_clear()
    yield
    desktop_files.installed.cache_clear()
    app_name.cache_clear()


@pytest.mark.parametrize("app_id, title, name", [
    ("org.gnome.Nautilus", "Downloads", "Files"),
    ("Code", "main.py - Visual Studio Code", "Visual Studio Code"),  # by the entry's window class
    ("chromium", "New Tab - Chromium", "My Chromium"),  # the user's own entry wins over the system's
    ("chrome-web.whatsapp.com__-Default", "WhatsApp", "WhatsApp"),  # a web app, by its address
    ("chrome-example.org__-Default", "Example", "example.org"),  # a web app with no entry
    ("steam_app_2416450", "Wardogs", "Wardogs"),  # a Steam game, by its window title
    ("mystery-app", "Mystery", "mystery-app"),
])
def test_names_apps_from_their_launcher_entries(app_id, title, name):
    assert app_name(App(None, app_id, title)) == name


def test_ghostwriters_own_window_and_unknown_apps():
    assert app_name(App(PROJECT / ".python" / "bin" / "python3.11", "pywebview", "Ghostwriter")) == "Ghostwriter"
    assert app_name(App(Path("/usr/bin/sometool"), "", "")) == "sometool"
    assert app_name(None) == "Unknown app"


def test_skips_files_that_arent_launcher_entries():
    assert "broken" not in {entry.id for entry in desktop_files.installed()}


def test_logs_apps_by_their_app_id():
    assert App(Path("/usr/lib/chromium/chromium"), "chrome-web.whatsapp.com__-Default", "").name \
        == "chrome-web.whatsapp.com__-Default"
    assert App(Path("/usr/bin/sometool"), "", "").name == "sometool"
