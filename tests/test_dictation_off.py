"""Turning dictation off: the hotkey goes back to being a normal key, and a recording in progress still gets typed."""

import pytest

from ghostwriter.app import NO_HOTKEY, Dictation, _Key, _Mode
from ghostwriter.settings import HOTKEYS, Settings
from ghostwriter.state import State


class Recorder:
    open_ms = 0.0

    def __init__(self) -> None:
        self.recording = False

    def start(self) -> None:
        self.recording = True

    def stop(self):
        self.recording = False
        return [0.0]


def _dictation() -> tuple[Dictation, Recorder, list[State]]:
    states: list[State] = []
    recorder = Recorder()
    dictation = Dictation(None, recorder, None, hotkey=HOTKEYS["Right Alt"], on_state=states.append)
    return dictation, recorder, states


def _hook_key(dictation: Dictation) -> int:
    hook = dictation._hook
    return hook.vk_code if hasattr(hook, "vk_code") else hook.key_code


def test_turning_dictation_off_lets_the_hotkey_work_normally():
    dictation, _, _ = _dictation()
    dictation.set_hotkey(None)
    assert _hook_key(dictation) == NO_HOTKEY
    dictation.set_hotkey(HOTKEYS["Right Ctrl"])  # back on
    assert _hook_key(dictation) == HOTKEYS["Right Ctrl"]


@pytest.mark.parametrize("held", [_Mode.HOLDING, _Mode.LOCKED])
def test_a_recording_in_progress_is_typed_out_when_dictation_turns_off(held):
    dictation, recorder, states = _dictation()
    dictation._on_key(_Key.PRESS)
    dictation._mode = held
    dictation._on_key(_Key.OFF)
    assert not recorder.recording
    assert dictation._mode is _Mode.IDLE
    assert dictation._clips.qsize() == 1  # handed to the typing thread
    assert states[-1] is State.WORKING


def test_a_lone_tap_is_dropped_when_dictation_turns_off():
    dictation, recorder, _ = _dictation()
    dictation._on_key(_Key.PRESS)
    dictation._mode = _Mode.TAPPED
    dictation._on_key(_Key.OFF)
    assert not recorder.recording and dictation._mode is _Mode.IDLE
    assert dictation._clips.empty()


def test_dictation_is_on_unless_turned_off(tmp_path):
    settings = Settings.load(tmp_path / "settings.json")
    assert settings.dictation
    settings.change("dictation", False)
    assert not Settings.load(tmp_path / "settings.json").dictation
    with pytest.raises(ValueError):
        settings.change("dictation", "off")
