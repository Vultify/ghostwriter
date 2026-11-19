"""A desktop's own hands-free key (Omarchy's Alt + Space): one press starts listening hands free, the next stops and
types, and a press during a hold locks it on like a double tap."""

from ghostwriter.app import Dictation, _Key, _Mode
from ghostwriter.settings import HOTKEYS
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
    return Dictation(None, recorder, None, hotkey=HOTKEYS["Right Alt"], on_state=states.append), recorder, states


def test_one_press_listens_hands_free_and_the_next_stops_and_types():
    dictation, recorder, states = _dictation()
    dictation._on_key(_Key.TOGGLE)
    assert recorder.recording and dictation._mode is _Mode.LOCKED
    assert states == [State.LOCKED]  # straight to hands free, so the start sound plays once
    dictation._on_key(_Key.TOGGLE)
    assert not recorder.recording and dictation._mode is _Mode.IDLE
    assert dictation._clips.qsize() == 1
    assert states == [State.LOCKED, State.WORKING]


def test_it_locks_on_a_hold_in_progress_and_letting_go_keeps_listening():
    dictation, recorder, states = _dictation()
    dictation._on_key(_Key.PRESS)
    dictation._on_key(_Key.TOGGLE)
    dictation._on_key(_Key.RELEASE)
    assert recorder.recording and dictation._mode is _Mode.LOCKED
    assert states == [State.LISTENING, State.LOCKED]


def test_it_works_with_double_tap_turned_off():
    dictation, recorder, _ = _dictation()
    dictation.hands_free = False
    dictation._on_key(_Key.TOGGLE)
    assert recorder.recording and dictation._mode is _Mode.LOCKED


def test_a_hands_free_recording_also_stops_with_a_tap_of_the_hotkey():
    dictation, recorder, _ = _dictation()
    dictation._on_key(_Key.TOGGLE)
    dictation._on_key(_Key.PRESS)
    dictation._on_key(_Key.RELEASE)
    assert not recorder.recording and dictation._mode is _Mode.IDLE
    assert dictation._clips.qsize() == 1
