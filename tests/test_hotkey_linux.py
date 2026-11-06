"""The Linux key reader, fed by stand-in keyboards (named pipes) so it runs without access to the real ones."""

import os
import time
from pathlib import Path
from unittest import mock

import pytest

from ghostwriter.linux import hotkey
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

    def wait_for(self, count: int, timeout: float = 3.0) -> list[str]:
        deadline = time.monotonic() + timeout
        while len(self.events) < count and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.05)  # room for any extra event that shouldn't be there
        return self.events


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
        hook = KeyHook(key, recorded.press, recorded.release)
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
