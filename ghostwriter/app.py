"""Hold Right Alt, talk, let go: Ghostwriter pastes what you said wherever the cursor is."""

import logging
import queue
import threading
import time
from collections.abc import Callable
from enum import Enum

import numpy as np

from ghostwriter import sounds, win32
from ghostwriter.dictionary import DictionaryFile
from ghostwriter.hotkey import KeyHook
from ghostwriter.indicator import Indicator
from ghostwriter.paster import Paster
from ghostwriter.recorder import Recorder
from ghostwriter.state import State
from ghostwriter.transcriber import SAMPLE_RATE, Transcriber
from ghostwriter.tray import Tray
from ghostwriter.win32 import user32

HOTKEY = win32.VK_RMENU
# A release sooner than this is a tap, not a hold. A lone tap is thrown away as accidental.
TAP_SECONDS = 0.3
# A second press this soon after a tap locks recording on, hands free.
DOUBLE_TAP_SECONDS = 0.4
# Recording stops on its own after this long, in case lock mode gets left on.
MAX_RECORDING_SECONDS = 15 * 60

log = logging.getLogger("ghostwriter")


class _Key(Enum):
    PRESS = "press"
    RELEASE = "release"
    TIMEOUT = "timeout"


class _Mode(Enum):
    IDLE = "idle"
    HOLDING = "holding"  # key down, recording
    TAPPED = "tapped"  # quick release; still recording in case a second press locks it on
    LOCKED = "locked"  # recording hands free until the next press
    RELEASING = "releasing"  # recording handed off; waiting for the key to come back up


class Dictation:
    """Turns hotkey presses into recordings, and recordings into pasted text.

    Hold to talk, or double tap to lock recording on and tap again to stop. Recording runs on
    one thread and transcribing plus pasting on another, so a new press can start recording
    while the last dictation is still being typed out.
    """

    def __init__(
        self,
        transcriber: Transcriber,
        recorder: Recorder,
        paster: Paster,
        hotkey: int = HOTKEY,
        allow_injected: bool = False,
        on_state: Callable[[State], None] = lambda state: None,
        dictionary: DictionaryFile | None = None,
    ) -> None:
        self.transcriber = transcriber
        self.recorder = recorder
        self.paster = paster
        self.on_state = on_state
        self.dictionary = dictionary or DictionaryFile()
        self.max_recording_seconds = MAX_RECORDING_SECONDS
        self._key_events: queue.Queue[_Key | None] = queue.Queue()
        self._clips: queue.Queue[np.ndarray | None] = queue.Queue()
        self._mode = _Mode.IDLE
        self._recording_started = 0.0
        self._tapped_at = 0.0
        self._unfinished = 0  # finished recordings not yet typed out
        self._state = State.READY
        self._state_lock = threading.Lock()
        self._hook = KeyHook(
            hotkey,
            on_press=lambda: self._key_events.put(_Key.PRESS),
            on_release=lambda: self._key_events.put(_Key.RELEASE),
            allow_injected=allow_injected,
        )

    def start(self) -> None:
        threading.Thread(target=self._handle_key_events, name="Recording", daemon=True).start()
        threading.Thread(target=self._handle_clips, name="Typing", daemon=True).start()
        self._hook.start()

    def stop(self) -> None:
        self._hook.stop()
        self._key_events.put(None)
        self._clips.put(None)

    def _update_state(self, unfinished_change: int = 0) -> None:
        with self._state_lock:
            self._unfinished += unfinished_change
            if self._mode in (_Mode.HOLDING, _Mode.TAPPED):
                state = State.LISTENING
            elif self._mode is _Mode.LOCKED:
                state = State.LOCKED
            else:
                state = State.WORKING if self._unfinished else State.READY
            if state is not self._state:
                self._state = state
                self.on_state(state)

    def _handle_key_events(self) -> None:
        while True:
            try:
                key = self._key_events.get(timeout=self._seconds_until_timeout())
            except queue.Empty:
                key = _Key.TIMEOUT
            if key is None:
                return
            try:
                self._on_key(key)
            except Exception:
                self._set_mode(_Mode.IDLE)
                log.exception("Recording failed")

    def _seconds_until_timeout(self) -> float | None:
        """How long to wait for a key before acting on our own, or None to wait as long as it takes."""
        now = time.perf_counter()
        if self._mode is _Mode.TAPPED:
            return max(0.0, self._tapped_at + DOUBLE_TAP_SECONDS - now)
        if self._mode in (_Mode.HOLDING, _Mode.LOCKED):
            return max(0.0, self._recording_started + self.max_recording_seconds - now)
        return None

    def _on_key(self, key: _Key) -> None:
        mode = self._mode
        if key is _Key.PRESS:
            if mode is _Mode.IDLE:
                self._start_recording()
            elif mode is _Mode.TAPPED:
                self._set_mode(_Mode.LOCKED)
                log.info("Locked on, hands free. Tap Right Alt to stop.")
            elif mode is _Mode.LOCKED:
                self._finish_recording(then=_Mode.RELEASING)
        elif key is _Key.RELEASE:
            if mode is _Mode.HOLDING:
                if time.perf_counter() - self._recording_started >= TAP_SECONDS:
                    self._finish_recording(then=_Mode.IDLE)
                else:
                    self._tapped_at = time.perf_counter()
                    self._set_mode(_Mode.TAPPED)
            elif mode is _Mode.RELEASING:
                self._set_mode(_Mode.IDLE)
        elif mode is _Mode.TAPPED:
            self._discard_recording()
        elif mode in (_Mode.HOLDING, _Mode.LOCKED):
            log.info("Recording hit the %d minute limit", self.max_recording_seconds // 60)
            self._finish_recording(then=_Mode.RELEASING if mode is _Mode.HOLDING else _Mode.IDLE)

    def _set_mode(self, mode: _Mode) -> None:
        self._mode = mode
        self._update_state()

    def _start_recording(self) -> None:
        self.recorder.start()
        self._recording_started = time.perf_counter()
        self._set_mode(_Mode.HOLDING)
        log.info("Listening (mic opened in %.0f ms)", self.recorder.open_ms)

    def _finish_recording(self, then: _Mode) -> None:
        self._mode = then
        self._update_state(+1)  # show "typing" right away while the mic records its short tail
        self._clips.put(self.recorder.stop())

    def _discard_recording(self) -> None:
        self._set_mode(_Mode.IDLE)
        self.recorder.stop()
        log.info("Tap too short, ignored")

    def _handle_clips(self) -> None:
        while (audio := self._clips.get()) is not None:
            try:
                self._type_out(audio)
            except Exception:
                log.exception("Dictation failed")
            finally:
                self._update_state(-1)

    def _type_out(self, audio: np.ndarray) -> None:
        dictionary = self.dictionary.current()
        started = time.perf_counter()
        text = dictionary.apply(self.transcriber.transcribe(audio, prompt=dictionary.prompt))
        elapsed = time.perf_counter() - started
        if not text:
            log.info("Heard nothing")
            return
        log.info("%.1fs of audio, transcribed in %.2fs: %s", len(audio) / SAMPLE_RATE, elapsed, text)
        # The trailing space keeps back to back dictations from running together.
        if not self.paster.paste(text + " "):
            log.info("Clipboard changed during the paste, so it was left as is")


class StatusDisplay:
    """Shows each state change in the tray and the listening pill, with a sound when listening starts and stops."""

    def __init__(self, tray: Tray, indicator: Indicator) -> None:
        self.tray = tray
        self.indicator = indicator
        self._state = State.READY

    def __call__(self, state: State) -> None:
        # Locking on plays the start sound a second time, so a double tap is heard as two blips.
        if state.is_recording:
            sounds.play_start()
        elif self._state.is_recording:
            sounds.play_stop()
        self._state = state
        self.tray.set_state(state)
        self.indicator.show(None if state is State.READY else state)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    log.setLevel(logging.INFO)
    user32.SetProcessDpiAwarenessContext(win32.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)  # crisp on scaled screens
    log.info("Loading Whisper...")
    transcriber = Transcriber()
    transcriber.warm_up()

    quitting = threading.Event()
    recorder = Recorder()
    dictionary = DictionaryFile()
    dictionary.current()
    tray = Tray(on_quit=quitting.set)
    indicator = Indicator(level=lambda: recorder.level)
    dictation = Dictation(
        transcriber, recorder, Paster(), on_state=StatusDisplay(tray, indicator), dictionary=dictionary
    )
    tray.start()
    indicator.start()
    dictation.start()
    log.info("Ready. Hold Right Alt and talk. Quit from the tray icon or press Ctrl+C here.")
    try:
        while not quitting.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        dictation.stop()
        indicator.stop()
        tray.stop()
        log.info("Stopped.")
