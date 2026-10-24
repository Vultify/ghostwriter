"""Hold Right Alt, talk, let go: Ghostwriter pastes what you said wherever the cursor is."""

import logging
import queue
import threading
import time
from collections.abc import Callable

import numpy as np

from ghostwriter import sounds, win32
from ghostwriter.hotkey import KeyHook
from ghostwriter.indicator import Indicator
from ghostwriter.paster import Paster
from ghostwriter.recorder import Recorder
from ghostwriter.state import State
from ghostwriter.transcriber import SAMPLE_RATE, Transcriber
from ghostwriter.tray import Tray
from ghostwriter.win32 import user32

HOTKEY = win32.VK_RMENU
# Taps shorter than this are treated as accidental and thrown away.
MIN_HOLD_SECONDS = 0.25
# Temporary word list until Phase 6 moves it into dictionary.txt.
VOCABULARY = "Ghostwriter, Tulare, Castro Detailing, Supabase, Claude Code, Wardogs."

log = logging.getLogger("ghostwriter")


class Dictation:
    """Turns hotkey presses into recordings, and recordings into pasted text.

    Recording runs on one thread and transcribing plus pasting on another, so a new
    press can start recording while the last dictation is still being typed out.
    """

    def __init__(
        self,
        transcriber: Transcriber,
        recorder: Recorder,
        paster: Paster,
        hotkey: int = HOTKEY,
        allow_injected: bool = False,
        on_state: Callable[[State], None] = lambda state: None,
    ) -> None:
        self.transcriber = transcriber
        self.recorder = recorder
        self.paster = paster
        self.on_state = on_state
        self._key_events: queue.Queue[bool | None] = queue.Queue()
        self._clips: queue.Queue[np.ndarray | None] = queue.Queue()
        self._pressed_at: float | None = None
        self._unfinished = 0  # released recordings not yet typed out
        self._state = State.READY
        self._state_lock = threading.Lock()
        self._hook = KeyHook(
            hotkey,
            on_press=lambda: self._key_events.put(True),
            on_release=lambda: self._key_events.put(False),
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
            if self._pressed_at is not None:
                state = State.LISTENING
            else:
                state = State.WORKING if self._unfinished else State.READY
            if state is not self._state:
                self._state = state
                self.on_state(state)

    def _handle_key_events(self) -> None:
        while (pressed := self._key_events.get()) is not None:
            try:
                if pressed:
                    self._start_recording()
                else:
                    self._finish_recording()
            except Exception:
                self._pressed_at = None
                self._update_state()
                log.exception("Recording failed")

    def _start_recording(self) -> None:
        if self._pressed_at is not None:
            return
        self.recorder.start()
        self._pressed_at = time.perf_counter()
        self._update_state()
        log.info("Listening (mic opened in %.0f ms)", self.recorder.open_ms)

    def _finish_recording(self) -> None:
        if self._pressed_at is None:
            return
        held = time.perf_counter() - self._pressed_at
        self._pressed_at = None
        if held < MIN_HOLD_SECONDS:
            self._update_state()
            self.recorder.stop()
            log.info("Tap too short, ignored")
            return
        self._update_state(+1)  # show "typing" right away while the mic records its short tail
        self._clips.put(self.recorder.stop())

    def _handle_clips(self) -> None:
        while (audio := self._clips.get()) is not None:
            try:
                self._type_out(audio)
            except Exception:
                log.exception("Dictation failed")
            finally:
                self._update_state(-1)

    def _type_out(self, audio: np.ndarray) -> None:
        started = time.perf_counter()
        text = self.transcriber.transcribe(audio, prompt=VOCABULARY)
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
        if state is State.LISTENING:
            sounds.play_start()
        elif self._state is State.LISTENING:
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
    tray = Tray(on_quit=quitting.set)
    indicator = Indicator(level=lambda: recorder.level)
    dictation = Dictation(transcriber, recorder, Paster(), on_state=StatusDisplay(tray, indicator))
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
