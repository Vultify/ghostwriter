"""The Linux key reader, fed by stand-in keyboards (named pipes) so it runs without access to the real ones."""

import os
import signal
import time
from pathlib import Path
from unittest import mock

import pytest

from ghostwriter.linux import hotkey, omarchy_dictation
from ghostwriter.linux.hotkey import KeyHook

RIGHT_ALT = hotkey.HOTKEYS["Right Alt"]
RIGHT_CTRL = hotkey.HOTKEYS["Right Ctrl"]
LETTER_A = 30
REPEAT = 2


class FakeKeyboard:
    """A named pipe that stands in for /dev/input/eventN. A spare reader is held open so the writer never blocks."""

    def __init__(self, folder: Path, name: str) -> None:
        self.path = str(folder / name)
        os.mkfifo(self.path)
        self._spare = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
        self._writer = os.open(self.path, os.O_WRONLY)

    def key(self, code: int, value: int) -> None:
        os.write(self._writer, hotkey._EVENT.pack(0, 0, hotkey._EV_KEY, code, value)
                 + hotkey._EVENT.pack(0, 0, hotkey._EV_SYN, 0, 0))

    def tap(self, code: int) -> None:
        self.key(code, 1)
        self.key(code, 0)

    def unplug(self) -> None:
        os.close(self._writer)
        os.close(self._spare)


class Recorded:
    def __init__(self) -> None:
        self.events: list[str] = []

    def press(self) -> None:
        self.events.append("press")

    def release(self) -> None:
        self.events.append("release")

    def toggle(self) -> None:
        self.events.append("toggle")

    def wait_for(self, count: int, timeout: float = 3.0) -> list[str]:
        deadline = time.monotonic() + timeout
        while len(self.events) < count and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.05)  # room for any extra event that shouldn't be there
        return self.events


@pytest.fixture(autouse=True)
def omarchy_config(tmp_path, monkeypatch):
    """A config folder of the tests' own, so Omarchy's real dictation choice never decides how a test hears keys."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path / "config"


@pytest.fixture
def omarchy(tmp_path, monkeypatch, omarchy_config):
    """Ghostwriter picked as Omarchy's dictation app, with stand-ins for the commands Omarchy checks for, and the
    dictation signals caught the way the tray app catches them. Returns a function that picks or unpicks it."""
    commands = tmp_path / "bin"
    commands.mkdir()
    for name in ("ghostwriter", "omarchy-dictation", "omarchy-dictation-ghostwriter"):
        (commands / name).write_text("#!/bin/sh\n")
        (commands / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{commands}:{os.environ['PATH']}")
    numbers = list(omarchy_dictation.SIGNALS.values())
    handlers = {number: signal.getsignal(number) for number in numbers}
    hotkey.catch_signals()

    def pick(picked: bool = True) -> None:
        omarchy_dictation.backend_path().parent.mkdir(parents=True, exist_ok=True)
        omarchy_dictation.backend_path().write_text("ghostwriter\n" if picked else "voxtype\n")

    pick()
    yield pick
    for number, handler in handlers.items():
        signal.signal(number, handler)
    os.close(hotkey._signals_read)
    os.close(hotkey._signals_write)
    monkeypatch.setattr(hotkey, "_signals_read", -1)
    monkeypatch.setattr(hotkey, "_signals_write", -1)


def _send(command: str) -> None:
    os.kill(os.getpid(), omarchy_dictation.SIGNALS[command])


@pytest.fixture
def keyboards(tmp_path, monkeypatch):
    """The keyboards the reader finds, as a list tests can add to."""
    plugged_in: list[FakeKeyboard] = []
    monkeypatch.setattr(hotkey, "_keyboards", lambda include_injected: [board.path for board in plugged_in])
    monkeypatch.setattr(hotkey, "_RESCAN_SECONDS", 0.05)

    def plug_in(name: str = "event0") -> FakeKeyboard:
        board = FakeKeyboard(tmp_path, name)
        plugged_in.append(board)
        return board

    return plug_in


@pytest.fixture
def started():
    hooks: list[KeyHook] = []

    def start(recorded: Recorded, key: int = RIGHT_ALT) -> KeyHook:
        hook = KeyHook(key, recorded.press, recorded.release, on_toggle=recorded.toggle)
        hook.start()
        hooks.append(hook)
        return hook

    yield start
    for hook in hooks:
        hook.stop()


def test_reports_one_press_and_release_and_ignores_repeats_and_other_keys(keyboards, started):
    board = keyboards()
    recorded = Recorded()
    started(recorded)
    board.key(RIGHT_ALT, 1)
    board.key(RIGHT_ALT, REPEAT)
    board.key(RIGHT_ALT, REPEAT)
    board.tap(LETTER_A)
    board.key(RIGHT_ALT, 0)
    assert recorded.wait_for(2) == ["press", "release"]


def test_set_key_switches_to_the_new_key(keyboards, started):
    board = keyboards()
    recorded = Recorded()
    hook = started(recorded)
    hook.set_key(RIGHT_CTRL)
    board.tap(RIGHT_ALT)
    board.tap(RIGHT_CTRL)
    assert recorded.wait_for(2) == ["press", "release"]


def test_listens_to_every_keyboard_including_ones_plugged_in_later(keyboards, started):
    laptop = keyboards("event0")
    recorded = Recorded()
    started(recorded)
    laptop.tap(RIGHT_ALT)
    assert recorded.wait_for(2) == ["press", "release"]
    bluetooth = keyboards("event1")
    time.sleep(0.3)  # a few rescans
    bluetooth.tap(RIGHT_ALT)
    assert recorded.wait_for(4) == ["press", "release"] * 2


def test_a_keyboard_unplugged_mid_hold_lets_go(keyboards, started):
    board = keyboards()
    recorded = Recorded()
    started(recorded)
    board.key(RIGHT_ALT, 1)
    assert recorded.wait_for(1) == ["press"]
    board.unplug()
    assert recorded.wait_for(2) == ["press", "release"]


def test_stop_returns_right_away_and_reports_nothing_more(keyboards):
    board = keyboards()
    recorded = Recorded()
    hook = KeyHook(RIGHT_ALT, recorded.press, recorded.release)
    hook.start()
    started_at = time.monotonic()
    hook.stop()
    assert time.monotonic() - started_at < 0.5
    board.tap(RIGHT_ALT)
    assert recorded.wait_for(1, timeout=0.2) == []


def test_start_explains_the_input_group_when_no_keyboard_can_be_read(tmp_path, monkeypatch):
    locked = tmp_path / "event0"
    locked.touch(mode=0o000)
    monkeypatch.setattr(hotkey, "_keyboards", lambda include_injected: [str(locked)])
    if os.access(locked, os.R_OK):
        pytest.skip("running as root, so nothing is locked")
    with pytest.raises(PermissionError, match="input group"):
        KeyHook(RIGHT_ALT, print, print).start()


def test_finds_keyboards_with_a_hotkey_and_leaves_out_ones_programs_made(tmp_path, monkeypatch):
    laptop_keys = "20000 6000000000000020 0 0 10500f02100007 ff803078f900d401 feffffdfffcfffff fffffffffffffffe"
    devices = {
        "event2": ("platform/i8042/serio0/input/input2", laptop_keys),  # a real keyboard
        "event3": ("virtual/input/input9", laptop_keys),  # a keyboard a program made
        "event4": ("platform/lid/input/input0", "0"),  # the lid switch
    }
    sysfs = tmp_path / "class"
    sysfs.mkdir()
    for name, (parent, keys) in devices.items():
        device = tmp_path / "devices" / parent / name
        (device / "device" / "capabilities").mkdir(parents=True)
        (device / "device" / "capabilities" / "key").write_text(keys + "\n")
        (sysfs / name).symlink_to(device)
    monkeypatch.setattr(hotkey, "_SYSFS", sysfs)
    assert hotkey._keyboards(include_injected=False) == ["/dev/input/event2"]
    assert hotkey._keyboards(include_injected=True) == ["/dev/input/event2", "/dev/input/event3"]


@pytest.mark.parametrize("layout, uses_altgr", [
    (("us", "", ""), False),
    (("us", "", "compose:caps"), False),
    (("de", "", ""), True),
    (("us", "intl", ""), True),
    (("us,de", "", ""), True),
    (("de", "", "lv3:ralt_alt"), False),
])
def test_knows_which_layouts_make_right_alt_into_altgr(layout, uses_altgr):
    with mock.patch.object(hotkey, "_keyboard_layout", return_value=layout):
        assert hotkey.keyboard_uses_altgr() is uses_altgr
        assert hotkey.default_hotkey() == ("Right Ctrl" if uses_altgr else "Right Alt")


def test_omarchys_dictation_keys_drive_it_instead_of_the_keyboard(omarchy, keyboards, started):
    board = keyboards()
    recorded = Recorded()
    started(recorded)
    board.tap(RIGHT_ALT)  # Omarchy has the key, so Ghostwriter doesn't read it itself
    for command in ("start", "start", "stop", "toggle", "stop"):  # a second start or stop changes nothing
        _send(command)
    assert recorded.wait_for(3) == ["press", "release", "toggle"]


def test_omarchy_presses_sent_while_ghostwriter_starts_are_dropped(omarchy, keyboards, started):
    _send("start")
    _send("toggle")
    recorded = Recorded()
    started(recorded)
    _send("stop")
    assert recorded.wait_for(1, timeout=0.3) == []


def test_picking_or_unpicking_it_in_omarchys_menu_switches_over_live(omarchy, keyboards, started):
    board = keyboards()
    recorded = Recorded()
    started(recorded)
    _send("start")
    assert recorded.wait_for(1) == ["press"]
    omarchy(picked=False)  # Omarchy's key isn't ours anymore mid hold, so the hold ends
    assert recorded.wait_for(2) == ["press", "release"]
    time.sleep(0.2)
    _send("start")
    board.tap(RIGHT_ALT)
    assert recorded.wait_for(4) == ["press", "release"] * 2
    omarchy(picked=True)
    time.sleep(0.2)
    board.tap(RIGHT_ALT)
    _send("toggle")
    assert recorded.wait_for(5) == ["press", "release"] * 2 + ["toggle"]


def test_omarchys_keys_do_nothing_while_dictation_is_off(omarchy, keyboards, started):
    recorded = Recorded()
    started(recorded).set_key(0)
    _send("start")
    _send("toggle")
    assert recorded.wait_for(1, timeout=0.3) == []


def test_omarchys_keys_need_no_input_group(omarchy, tmp_path, monkeypatch):
    locked = tmp_path / "event0"
    locked.touch(mode=0o000)
    monkeypatch.setattr(hotkey, "_keyboards", lambda include_injected: [str(locked)])
    recorded = Recorded()
    hook = KeyHook(RIGHT_ALT, recorded.press, recorded.release)
    hook.start()  # no PermissionError
    try:
        _send("start")
        assert recorded.wait_for(1) == ["press"]
    finally:
        hook.stop()


def test_a_picked_ghostwriter_that_isnt_installed_leaves_the_keys_to_ghostwriter(omarchy, monkeypatch):
    assert omarchy_dictation.owns_keys()
    monkeypatch.setenv("PATH", "/usr/bin")  # Omarchy doesn't bind its keys without the ghostwriter command
    assert not omarchy_dictation.owns_keys()
    assert hotkey.desktop_keys() is None
