"""The tray ghost on Linux: it shows up in the desktop's tray with its menu, opens the menu on a left click, follows
changed settings, turns red while listening, and leaves when Ghostwriter stops. It needs a desktop with a tray, like
Omarchy's bar."""

import json
import subprocess
import sys
import time

import pytest
from gi.repository import Gio, GLib

from ghostwriter.paths import PROJECT
from ghostwriter.settings import Settings
from ghostwriter.linux import desktop, omarchy_dictation, tray_icon
from ghostwriter.state import State
from ghostwriter.tray import Tray

WATCHER = "org.kde.StatusNotifierWatcher"  # the tray, as every Linux desktop names it
ITEM = "org.kde.StatusNotifierItem"
MENU = "com.canonical.dbusmenu"

bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)


@pytest.fixture(autouse=True)
def keys_not_omarchys(tmp_path, monkeypatch):
    """Ghostwriter's own hotkey drives the tray here, even when it's the user's pick for Omarchy's dictation keys."""
    monkeypatch.setattr(omarchy_dictation, "backend_path", lambda: tmp_path / "dictation")


def _call(name: str, path: str, interface: str, method: str, args: GLib.Variant | None, reply: str):
    return bus.call_sync(name, path, interface, method, args, GLib.VariantType(reply), Gio.DBusCallFlags.NONE, 2000,
                         None).unpack()


def _property(name: str, path: str, interface: str, prop: str):
    return _call(name, path, "org.freedesktop.DBus.Properties", "Get", GLib.Variant("(ss)", (interface, prop)),
                 "(v)")[0]


def _has_tray() -> bool:
    return _call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner",
                 GLib.Variant("(s)", (WATCHER,)), "(b)")[0]


def _our_item(owner: str | None = None) -> str | None:
    """The tray item a program made, found by its bus connection (this process's own unless owner is given)."""
    for item in _property(WATCHER, "/StatusNotifierWatcher", WATCHER, "RegisteredStatusNotifierItems"):
        if item.startswith((owner or bus.get_unique_name()) + "/"):
            return item.partition("/")[2]
    return None


def _menu(path: str) -> list[tuple[str, bool | None, int]]:
    """Each menu entry's label, whether it's checked (None if it can't be), and its id."""
    menu = _property(bus.get_unique_name(), "/" + path, ITEM, "Menu")
    _, layout = _call(bus.get_unique_name(), menu, MENU, "GetLayout", GLib.Variant("(iias)", (0, -1, [])),
                      "(u(ia{sv}av))")
    entries = []

    def walk(node):
        row, props, children = node
        if "label" in props:
            entries.append((props["label"], bool(props["toggle-state"]) if props.get("toggle-type") else None,
                            row))
        for child in children:
            walk(child)

    walk(layout)
    return entries


def _click(path: str, label: str) -> None:
    """Click a menu row the way the bar does."""
    menu = _property(bus.get_unique_name(), "/" + path, ITEM, "Menu")
    row = next(row for text, _, row in _menu(path) if text == label)
    click = GLib.Variant("(isvu)", (row, "clicked", GLib.Variant("s", ""), 0))
    _call(bus.get_unique_name(), menu, MENU, "Event", click, "()")


def _wait_for(check, seconds: float = 5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        found = check()
        if found:
            return found
        time.sleep(0.1)
    return check()


needs_a_tray = pytest.mark.skipif(not _has_tray(), reason="this desktop has no tray")
# The on/off rows in the menu, all on by default.
SWITCHES = {"Dictation": "dictation", "Sounds": "sounds", "Listening pill": "pill",
            "Lower other sounds while listening": "other_sounds", "Save history": "history"}


@needs_a_tray
def test_the_ghost_sits_in_the_tray_with_its_menu(tmp_path, monkeypatch):
    monkeypatch.setattr(tray_icon, "STATUS_PATH", tmp_path / "status.json")  # not the real panel's
    settings = Settings(path=tmp_path / "settings.json")
    opened = []
    tray = Tray(settings, ["Studio mic"], on_quit=lambda: None, files={"Open log": tmp_path},
                on_open=lambda: opened.append(True))
    tray.start()
    try:
        tray.set_state(State.READY)
        path = _wait_for(_our_item)
        assert path, "the ghost never showed up in the tray"
        assert "hold Right Alt to talk" in _property(bus.get_unique_name(), "/" + path, ITEM, "Title")

        menu = _menu(path)
        labels = [label for label, *_ in menu]
        assert labels[0] == "Open Ghostwriter" and labels[-1] == "Quit Ghostwriter"
        assert {"Hotkey", "Microphone", "Open log", "Check for updates"} <= set(labels)
        checked = {label for label, on, _ in menu if on}
        assert checked == {"Right Alt", f"{desktop.NAME} default", *SWITCHES}

        settings.hotkey = "Right Ctrl"  # as if the app window changed it
        tray.refresh()
        assert _wait_for(lambda: ("Right Ctrl", True) in [(label, on) for label, on, _ in _menu(path)])
        assert "hold Right Ctrl to talk" in _property(bus.get_unique_name(), "/" + path, ITEM, "Title")

        for label, setting in SWITCHES.items():  # a click in the menu turns each one off, checkmark and all
            _click(path, label)
            assert _wait_for(lambda: (label, False) in [(text, on) for text, on, _ in _menu(path)])
        assert (settings.dictation, settings.sounds, settings.pill, settings.other_sounds, settings.history) == (
            False, False, False, 100, False)
        _click(path, "Lower other sounds while listening")
        assert settings.other_sounds == 10  # back on, at the default level

        status = json.loads((tmp_path / "status.json").read_text())  # what the Omarchy panel reads
        assert status["state"] == "ready" and status["values"]["dictation"] is False
        assert status["settings"] == str(settings.path) and status["hotkeys"][0] == "Right Alt"
        assert status["microphones"] == ["Studio mic"] and status["defaultMicrophone"] == f"{desktop.NAME} default"
        faded = _property(bus.get_unique_name(), "/" + path, ITEM, "IconPixmap")
        _click(path, "Dictation")  # back on, and the ghost is no longer faded
        assert _wait_for(lambda: _property(bus.get_unique_name(), "/" + path, ITEM, "IconPixmap") != faded)

        assert _property(bus.get_unique_name(), "/" + path, ITEM, "ItemIsMenu")  # a left click opens the menu
        _call(bus.get_unique_name(), "/" + path, ITEM, "SecondaryActivate", GLib.Variant("(ii)", (0, 0)), "()")
        assert opened  # a middle click runs the menu's first row, Open Ghostwriter

        ready_icon = _property(bus.get_unique_name(), "/" + path, ITEM, "IconPixmap")
        assert {(width, height) for width, height, _ in ready_icon} >= {(16, 16), (64, 64)}
        tray.set_state(State.LISTENING)
        assert _wait_for(lambda: _property(bus.get_unique_name(), "/" + path, ITEM, "IconPixmap") != ready_icon)
    finally:
        tray.stop()
    assert json.loads((tmp_path / "status.json").read_text())["state"] == "stopped"


@needs_a_tray
def test_the_ghost_leaves_the_tray_even_after_a_crash(tmp_path):
    program = subprocess.Popen(
        [sys.executable, "-c",
         "from pathlib import Path; import sys, time; from gi.repository import Gio; "
         "from ghostwriter.settings import Settings; from ghostwriter.state import State; "
         "from ghostwriter.tray import Tray; "
         "from ghostwriter.linux import tray_icon; "
         "tray_icon.STATUS_PATH = Path(sys.argv[1]).with_name('status.json'); "
         "tray = Tray(Settings(path=Path(sys.argv[1])), [], on_quit=lambda: None, files={}); "
         "tray.start(); tray.set_state(State.READY); "
         "print(Gio.bus_get_sync(Gio.BusType.SESSION, None).get_unique_name(), flush=True); time.sleep(30)",
         str(tmp_path / "settings.json")],
        cwd=PROJECT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    try:
        owner = program.stdout.readline().strip()
        assert _wait_for(lambda: _our_item(owner)), "the ghost never showed up in the tray"
    finally:
        program.kill()  # no chance to tidy up, like a crash
        program.wait()
    assert _wait_for(lambda: _our_item(owner) is None), "a dead ghost stayed in the tray"
