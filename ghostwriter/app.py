"""Hold Right Alt, talk, let go: Ghostwriter pastes what you said wherever the cursor is."""

import logging
import os
import queue
import sqlite3
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from logging.handlers import RotatingFileHandler

import numpy as np

from ghostwriter import __version__, models, sounds, startup, updates
from ghostwriter.audio import SAMPLE_RATE, wav_bytes
from ghostwriter.dictionary import DICTIONARY_PATH, DictionaryFile
from ghostwriter.history import History
from ghostwriter.indicator import Indicator
from ghostwriter.paths import LOG_PATH, RECORDINGS_DIR
from ghostwriter.recorder import Recorder, list_microphones
from ghostwriter.settings import Settings
from ghostwriter.speech import SpeechEngine
from ghostwriter.state import State
from ghostwriter.system import desktop, install
from ghostwriter.system import hotkey as system_hotkey
from ghostwriter.system import paster as system_paster
from ghostwriter.transcriber import Transcriber, gpu_available
from ghostwriter.tray import Tray
from ghostwriter.window import close_window, open_window

HOTKEY = system_hotkey.HOTKEYS["Right Alt"]
INSTANCE_NAME = "Ghostwriter"
TRAY_ONLY_FLAG = "--tray"  # start in the tray without opening the window
# With this set, every dictation's audio is also saved in recordings\, for scripts\compare_engines.py.
KEEP_RECORDINGS_VARIABLE = "GHOSTWRITER_KEEP_RECORDINGS"
NO_ENGINE_MESSAGE = (
    "Ghostwriter couldn't find its speech engine for this graphics card. Run the install command again to get it:\n\n"
    + install.INSTALL_COMMAND
)
DOWNLOAD_MESSAGE = (
    "Downloading the speech model (about {size}). This only happens once and can take a few minutes. "
    "I'll let you know when it's ready."
)
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
        transcriber: SpeechEngine | Transcriber,
        recorder: Recorder,
        paster: system_paster.Paster,
        hotkey: int = HOTKEY,
        allow_injected: bool = False,
        on_state: Callable[[State], None] = lambda state: None,
        dictionary: DictionaryFile | None = None,
        history: History | None = None,
    ) -> None:
        self.transcriber = transcriber
        self.recorder = recorder
        self.paster = paster
        self.on_state = on_state
        self.dictionary = dictionary or DictionaryFile()
        self.history = history  # None saves nothing, like when history is turned off
        self.keep_recordings = False
        self.max_recording_seconds = MAX_RECORDING_SECONDS
        self.hands_free = True  # with this off, a double tap is just two ignored taps
        self._key_events: queue.Queue[_Key | None] = queue.Queue()
        self._clips: queue.Queue[np.ndarray | None] = queue.Queue()
        self._mode = _Mode.IDLE
        self._recording_started = 0.0
        self._tapped_at = 0.0
        self._unfinished = 0  # finished recordings not yet typed out
        self._state = State.READY
        self._state_lock = threading.Lock()
        self._hook = system_hotkey.KeyHook(
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

    def set_hotkey(self, key_code: int) -> None:
        self._hook.set_key(key_code)

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
                log.info("Locked on, hands free. Tap the hotkey to stop.")
            elif mode is _Mode.LOCKED:
                self._finish_recording(then=_Mode.RELEASING)
        elif key is _Key.RELEASE:
            if mode is _Mode.HOLDING:
                if time.perf_counter() - self._recording_started >= TAP_SECONDS:
                    self._finish_recording(then=_Mode.IDLE)
                elif not self.hands_free:
                    self._discard_recording()
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
        if self.keep_recordings:
            RECORDINGS_DIR.mkdir(exist_ok=True)
            (RECORDINGS_DIR / f"{datetime.now():%Y-%m-%d %H-%M-%S}.wav").write_bytes(wav_bytes(audio))
        dictionary = self.dictionary.current()
        started = time.perf_counter()
        text = dictionary.apply(self.transcriber.transcribe(audio, prompt=dictionary.prompt))
        elapsed = time.perf_counter() - started
        if not text:
            log.info("Heard nothing")
            return
        seconds = len(audio) / SAMPLE_RATE
        program = system_paster.foreground_app()
        log.info("%.1fs of audio, transcribed in %.2fs, pasting into %s: %s",
                 seconds, elapsed, program.name if program else "an unknown app", text)
        try:
            # The trailing space keeps back to back dictations from running together.
            if not self.paster.paste(text + " "):
                log.info("Clipboard changed during the paste, so it was left as is")
        finally:
            # Saved even when the paste fails, so the words can still be copied from History.
            if history := self.history:
                self._save(history, text, program, seconds)

    @staticmethod
    def _save(history: History, text: str, program: system_paster.App | None, seconds: float) -> None:
        try:
            history.add(text, system_paster.app_name(program), seconds)
        except sqlite3.Error:
            log.exception("Couldn't save the dictation to history")


class StatusDisplay:
    """Shows each state change in the tray and the listening pill, with a sound when listening starts and stops."""

    def __init__(self, tray: Tray, indicator: Indicator, settings: Settings) -> None:
        self.tray = tray
        self.indicator = indicator
        self.settings = settings
        self._state = State.READY

    def __call__(self, state: State) -> None:
        # Locking on plays the start sound a second time, so a double tap is heard as two blips.
        if self.settings.sounds:
            if state.is_recording:
                sounds.play_start(self.settings.sound)
            elif self._state.is_recording:
                sounds.play_stop(self.settings.sound)
        self._state = state
        self.tray.set_state(state)
        self.indicator.show(state if state is not State.READY and self.settings.pill else None)


def main() -> None:
    _set_up_logging()
    if not claim_single_instance():
        open_window()  # starting it again, like from the Start menu, just opens the window
        return
    try:
        _run()
    except Exception as error:
        log.exception("Ghostwriter stopped because of an error")
        desktop.show_error(f"Ghostwriter stopped because of an error:\n\n{error}\n\nDetails are in {LOG_PATH}")


def _run() -> None:
    desktop.prepare()
    has_nvidia = gpu_available()
    if not models.available(has_nvidia):
        log.error("No NVIDIA GPU, and whisper.cpp isn't installed")
        desktop.show_error(NO_ENGINE_MESSAGE)
        return
    settings = Settings.load()
    quitting = threading.Event()
    tray = Tray(settings, list_microphones(), on_quit=quitting.set,
                files={"Edit dictionary": DICTIONARY_PATH, "Open log": LOG_PATH},
                on_check_updates=lambda: threading.Thread(target=check_for_updates, args=(tray,), daemon=True).start(),
                on_open=open_window)
    tray.start()  # the ghost shows up right away while Whisper loads
    engine = models.resolve(settings.engine, has_nvidia)
    first_run = not models.downloaded(engine, has_nvidia)
    # Written before the window opens, so on the first run it opens on the welcome and shows the download.
    startup.write(model="downloading" if first_run else "loading", engine=engine, first_run=first_run)
    show_window = TRAY_ONLY_FLAG not in sys.argv
    if show_window:
        open_window()
    if first_run:
        log.info("Downloading the speech model for %s for the first time", engine)
        if not show_window:
            tray.notify(DOWNLOAD_MESSAGE.format(size=models.size(engine, has_nvidia)))

    log.info("Loading Whisper with %s...", engine)
    speech = SpeechEngine(has_nvidia)
    try:
        speech.load(engine, first_run)
    except Exception:
        startup.write(model="failed", engine=engine, first_run=first_run)
        raise
    recorder = Recorder(microphone=settings.microphone)
    dictionary = DictionaryFile()
    dictionary.current()
    history = History()
    indicator = Indicator(level=lambda: recorder.level)
    dictation = Dictation(
        speech, recorder, system_paster.Paster(), hotkey=settings.hotkey_code,
        on_state=StatusDisplay(tray, indicator, settings), dictionary=dictionary,
    )

    def apply_settings() -> None:
        dictation.set_hotkey(settings.hotkey_code)
        dictation.hands_free = settings.hands_free
        dictation.max_recording_seconds = settings.hands_free_minutes * 60
        dictation.history = history if settings.history else None
        recorder.microphone = settings.microphone
        speech.switch_to(models.resolve(settings.engine, has_nvidia))
        tray.refresh()
        log.info("Settings: hotkey %s, mic %s, sounds %s, pill %s, hands free %s, history %s, engine %s",
                 settings.hotkey, settings.microphone or f"{desktop.NAME} default",
                 settings.sound if settings.sounds else "off", "on" if settings.pill else "off",
                 f"on, up to {settings.hands_free_minutes} min" if settings.hands_free else "off",
                 "on" if settings.history else "off", settings.engine)

    dictation.keep_recordings = KEEP_RECORDINGS_VARIABLE in os.environ
    if dictation.keep_recordings:
        log.info("Saving every dictation's audio in %s", RECORDINGS_DIR)
    tray.on_change = apply_settings
    apply_settings()
    indicator.start()
    dictation.start()
    tray.set_state(State.READY)
    startup.write(model="ready", engine=engine, device=speech.device)
    log.info("Ready. Hold %s to talk, or double tap it for hands free.", settings.hotkey)
    if first_run:
        tray.notify(f"Ready! Hold {settings.hotkey} to talk, or double tap it for hands free.")
    try:
        while not quitting.wait(0.5):
            if settings.reload_if_changed():  # saved by the app window
                apply_settings()
    except KeyboardInterrupt:
        pass
    finally:
        close_window()
        dictation.stop()
        speech.close()
        indicator.stop()
        tray.stop()
        log.info("Stopped.")


def check_for_updates(tray: Tray) -> None:
    """Ask GitHub for the latest release and offer to install it. Runs on its own thread, since it goes online."""
    if updates.is_git_checkout():
        tray.notify("This copy of Ghostwriter is a git checkout, so update it with git pull instead.")
        return
    try:
        latest = updates.latest_version()
    except Exception as error:
        log.warning("Couldn't check for updates: %s", error)
        tray.notify("Couldn't check for updates. Check your internet connection and try again.")
        return
    if not updates.is_newer(latest):
        tray.notify(f"You're up to date (version {__version__}).")
        return
    question = (f"Ghostwriter {latest} is available (you have {__version__}).\n\n"
                "Update now? Ghostwriter will close, update, and start again.")
    if desktop.ask_yes_no(question):
        log.info("Updating to %s", latest)
        updates.start_update()


def claim_single_instance(name: str = INSTANCE_NAME) -> bool:
    """Return False if another copy of Ghostwriter is already running."""
    return desktop.claim_single_instance(name)


def _set_up_logging() -> None:
    """Log to logs/ghostwriter.log, and to the terminal too when there is one."""
    LOG_PATH.parent.mkdir(exist_ok=True)
    handlers: list[logging.Handler] = [RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8")]
    if sys.stderr is None:
        # Started with no terminal: give libraries that print progress (like the model download) somewhere to write.
        sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
    else:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
                        handlers=handlers)
    log.setLevel(logging.INFO)

