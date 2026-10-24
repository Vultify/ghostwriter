"""Hold Right Alt, talk, let go: Ghostwriter pastes what you said wherever the cursor is."""

import logging
import queue
import threading
import time

import numpy as np

from ghostwriter import win32
from ghostwriter.hotkey import KeyHook
from ghostwriter.paster import Paster
from ghostwriter.recorder import Recorder
from ghostwriter.transcriber import SAMPLE_RATE, Transcriber

HOTKEY = win32.VK_RMENU
# Taps shorter than this are treated as accidental and thrown away.
MIN_HOLD_SECONDS = 0.25
# Temporary word list until Phase 5 moves it into dictionary.txt.
VOCABULARY = "Ghostwriter, Tulare, Castro Detailing, Supabase, Claude Code."

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
    ) -> None:
        self.transcriber = transcriber
        self.recorder = recorder
        self.paster = paster
        self._key_events: queue.Queue[bool | None] = queue.Queue()
        self._clips: queue.Queue[np.ndarray | None] = queue.Queue()
        self._pressed_at: float | None = None
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

    def _handle_key_events(self) -> None:
        while (pressed := self._key_events.get()) is not None:
            try:
                if pressed:
                    self._start_recording()
                else:
                    self._finish_recording()
            except Exception:
                self._pressed_at = None
                log.exception("Recording failed")

    def _start_recording(self) -> None:
        if self._pressed_at is not None:
            return
        self.recorder.start()
        self._pressed_at = time.perf_counter()
        log.info("Listening (mic opened in %.0f ms)", self.recorder.open_ms)

    def _finish_recording(self) -> None:
        if self._pressed_at is None:
            return
        held = time.perf_counter() - self._pressed_at
        self._pressed_at = None
        audio = self.recorder.stop()
        if held < MIN_HOLD_SECONDS:
            log.info("Tap too short, ignored")
            return
        self._clips.put(audio)

    def _handle_clips(self) -> None:
        while (audio := self._clips.get()) is not None:
            try:
                self._type_out(audio)
            except Exception:
                log.exception("Dictation failed")

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


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    log.setLevel(logging.INFO)
    log.info("Loading Whisper...")
    transcriber = Transcriber()
    transcriber.warm_up()
    dictation = Dictation(transcriber, Recorder(), Paster())
    dictation.start()
    log.info("Ready. Hold Right Alt and talk. Press Ctrl+C here to quit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        dictation.stop()
        log.info("Stopped.")
