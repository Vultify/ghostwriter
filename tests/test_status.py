"""The tray icon, listening pill, and sounds: they show the right state and never steal focus."""

import threading
import time
import wave

from conftest import press_key, pump_until

from ghostwriter import sounds, win32
from ghostwriter.app import Dictation
from ghostwriter.indicator import Indicator
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


def test_tray_starts_switches_state_and_stops():
    tray = Tray(on_quit=lambda: None)
    tray.start()
    time.sleep(0.3)
    for state in (State.LISTENING, State.WORKING, State.READY):
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
    def paste(self, text: str) -> bool:
        return True


def _states_for_a_press(hold_seconds: float) -> list[State]:
    states: list[State] = []
    back_to_ready = threading.Event()

    def record(state: State) -> None:
        states.append(state)
        if state is State.READY:
            back_to_ready.set()

    dictation = Dictation(FakeTranscriber(), FakeRecorder(), FakePaster(), allow_injected=True, on_state=record)
    dictation.start()
    try:
        press_key(win32.VK_RMENU)
        time.sleep(hold_seconds)
        press_key(win32.VK_RMENU, release=True)
        assert back_to_ready.wait(3)
    finally:
        dictation.stop()
    return states


def test_a_dictation_goes_listening_then_typing_then_ready():
    assert _states_for_a_press(0.4) == [State.LISTENING, State.WORKING, State.READY]


def test_a_quick_tap_goes_straight_back_to_ready():
    assert _states_for_a_press(0.05) == [State.LISTENING, State.READY]
