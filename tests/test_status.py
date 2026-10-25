"""The tray icon, listening pill, and sounds: they show the right state and never steal focus."""

import time
import wave

from conftest import press_key, pump_until

from ghostwriter import sounds, win32
from ghostwriter.app import Dictation
from ghostwriter.indicator import Indicator
from ghostwriter.settings import Settings
from ghostwriter.state import State
from ghostwriter.tray import Tray
from ghostwriter.win32 import user32


def test_pill_shows_and_hides_without_taking_focus(text_box):
    root, box = text_box
    front = user32.GetForegroundWindow()
    indicator = Indicator(level=lambda: 0.05)
    indicator.start()
    try:
        indicator.show(State.LISTENING)
        pump_until(root, lambda: False, timeout=0.4)
        assert user32.IsWindowVisible(indicator.window)
        assert user32.GetForegroundWindow() == front
        style = user32.GetWindowLongPtrW(indicator.window, win32.GWL_EXSTYLE)
        assert style & win32.WS_EX_NOACTIVATE and style & win32.WS_EX_TRANSPARENT

        indicator.show(None)
        pump_until(root, lambda: False, timeout=0.4)
        assert not user32.IsWindowVisible(indicator.window)
    finally:
        indicator.stop()


def test_tray_starts_switches_state_and_stops(tmp_path):
    tray = Tray(Settings(path=tmp_path / "settings.json"), ["Mic A"], on_quit=lambda: None, files={})
    tray.start()
    time.sleep(0.3)
    for state in (State.LISTENING, State.LOCKED, State.WORKING, State.READY):
        tray.set_state(state)
    tray.stop()


def test_sounds_are_short_and_play():
    for name in ("start", "stop"):
        with wave.open(str(sounds.ASSETS / f"{name}.wav")) as clip:
            assert clip.getnframes() / clip.getframerate() < 0.2
    sounds.play_start()
    sounds.play_stop()


class FakeRecorder:
    open_ms = 0.0

    def start(self) -> None:
        pass

    def stop(self):
        return [0.0]


class FakeTranscriber:
    def transcribe(self, audio, prompt=None) -> str:
        return "hello"


class FakePaster:
    def __init__(self) -> None:
        self.pasted: list[str] = []

    def paste(self, text: str) -> bool:
        self.pasted.append(text)
        return True


PRESS, RELEASE = "press", "release"
SETTLE_SECONDS = 0.8  # longer than the double tap window, so a lone tap has been decided


def _play(*steps: tuple[str, float], max_recording_seconds: float | None = None) -> tuple[list[State], int]:
    """Press and release Right Alt as listed (each step waits after itself), then return the states and paste count."""
    states: list[State] = []
    paster = FakePaster()
    dictation = Dictation(FakeTranscriber(), FakeRecorder(), paster, allow_injected=True, on_state=states.append)
    if max_recording_seconds:
        dictation.max_recording_seconds = max_recording_seconds
    dictation.start()
    try:
        for action, wait in steps:
            press_key(win32.VK_RMENU, release=action == RELEASE)
            time.sleep(wait)
        deadline = time.perf_counter() + 5
        settled_count, settled_at = -1, time.perf_counter()
        while time.perf_counter() < deadline:
            if len(states) != settled_count:
                settled_count, settled_at = len(states), time.perf_counter()
            elif states and states[-1] is State.READY and time.perf_counter() - settled_at > SETTLE_SECONDS:
                break
            time.sleep(0.02)
    finally:
        dictation.stop()
    return states, len(paster.pasted)


def test_hold_to_talk_goes_listening_then_typing_then_ready():
    assert _play((PRESS, 0.5), (RELEASE, 0)) == ([State.LISTENING, State.WORKING, State.READY], 1)


def test_a_lone_quick_tap_is_thrown_away():
    assert _play((PRESS, 0.05), (RELEASE, 0)) == ([State.LISTENING, State.READY], 0)


def test_double_tap_locks_on_until_the_next_tap():
    states, pastes = _play(
        (PRESS, 0.05), (RELEASE, 0.1),  # first tap
        (PRESS, 0.05), (RELEASE, 1.0),  # second tap locks on; letting go doesn't stop it
        (PRESS, 0.05), (RELEASE, 0),  # one more tap stops and types
    )
    assert states == [State.LISTENING, State.LOCKED, State.WORKING, State.READY]
    assert pastes == 1


def test_a_second_tap_after_the_window_starts_fresh_instead_of_locking():
    states, pastes = _play((PRESS, 0.05), (RELEASE, 0.7), (PRESS, 0.5), (RELEASE, 0))
    assert states == [State.LISTENING, State.READY, State.LISTENING, State.WORKING, State.READY]
    assert pastes == 1


def test_lock_mode_stops_on_its_own_at_the_time_limit():
    states, pastes = _play((PRESS, 0.05), (RELEASE, 0.1), (PRESS, 0.05), (RELEASE, 0), max_recording_seconds=1.0)
    assert states == [State.LISTENING, State.LOCKED, State.WORKING, State.READY]
    assert pastes == 1
