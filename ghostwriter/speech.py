"""The speech engine Ghostwriter dictates with: faster-whisper on NVIDIA cards, or whisper.cpp on any graphics card.

Settings can switch engines while Ghostwriter runs. The new one loads in the background while the old one keeps
working, so dictation never stops, and startup.json keeps the app window up to date on the download.
"""

import logging
import threading
import time
from pathlib import Path

import numpy as np

from ghostwriter import models, startup, whisper_cpp
from ghostwriter.models import DownloadProgress
from ghostwriter.paths import STARTUP_PATH
from ghostwriter.transcriber import Transcriber, model_path
from ghostwriter.whisper_cpp import WhisperCpp

log = logging.getLogger("ghostwriter")


class SpeechEngine:
    def __init__(self, has_nvidia: bool, status_path: Path = STARTUP_PATH) -> None:
        self.has_nvidia = has_nvidia  # picks which whisper.cpp model to use
        self.status_path = status_path  # startup.json, where the window follows a switch
        self.name = ""
        self._engine: Transcriber | WhisperCpp | None = None
        self._wanted = ""
        self._failed = ""  # an engine that couldn't load isn't retried until it's picked again
        self._switching = False
        self._lock = threading.Lock()  # guards the switch bookkeeping
        self._in_use = threading.Lock()  # held while transcribing, so an engine is never closed mid dictation

    @property
    def device(self) -> str:
        """The graphics whisper.cpp runs on; faster-whisper leaves this to nvidia-smi."""
        return getattr(self._engine, "device", "")

    def load(self, engine: str, first_run: bool = False) -> None:
        """Load an engine and wait until it's ready, for startup."""
        self._engine = load_engine(engine, self.has_nvidia, first_run, self.status_path)
        self.name = self._wanted = engine

    def transcribe(self, audio: np.ndarray, prompt: str | None = None) -> str:
        with self._in_use:
            return self._engine.transcribe(audio, prompt=prompt)

    def switch_to(self, engine: str) -> None:
        """Start using another engine. It loads in the background; asking for the running one does nothing."""
        with self._lock:
            if engine == self.name:
                self._failed = ""
            if engine == self._failed:
                return
            self._wanted = engine
            if engine == self.name or self._switching:
                return
            self._switching = True
        threading.Thread(target=self._switch, name="Engine switch", daemon=True).start()

    def close(self) -> None:
        with self._in_use:
            if self._engine:
                self._engine.close()

    def _switch(self) -> None:
        while True:
            with self._lock:
                engine = self._wanted
                if engine == self.name:
                    self._switching = False
                    return
            log.info("Switching to %s", engine)
            try:
                new = load_engine(engine, self.has_nvidia, path=self.status_path)
            except Exception:
                log.exception("Couldn't switch to %s", engine)
                startup.write(self.status_path, model="failed", engine=engine)
                with self._lock:
                    self._failed = engine
                    self._switching = False
                return
            with self._in_use:
                old, self._engine, self.name = self._engine, new, engine
            old.close()
            startup.write(self.status_path, model="ready", engine=engine, device=self.device)
            log.info("Now dictating with %s", engine)


def load_engine(engine: str, has_nvidia: bool, first_run: bool = False,
                path: Path = STARTUP_PATH) -> Transcriber | WhisperCpp:
    """Download the engine's model if needed, load it onto the graphics card, and warm it up."""
    status = {"engine": engine, "first_run": first_run}
    startup.write(path, model="loading" if models.downloaded(engine, has_nvidia) else "downloading", **status)
    report = _download_reporter(status, path)
    if engine == models.FASTER_WHISPER:
        folder = model_path(report)
        startup.write(path, model="loading", **status)
        loaded = Transcriber(folder)
    else:
        model, vad = whisper_cpp.model_paths(models.whisper_cpp_model(has_nvidia), report)
        startup.write(path, model="loading", **status)
        loaded = WhisperCpp(model, vad)
    loaded.warm_up()
    return loaded


def _download_reporter(status: dict, path: Path = STARTUP_PATH, every: float = 0.25) -> DownloadProgress:
    """Save a model download's progress for the window, a few times a second at most."""
    lock = threading.Lock()
    last = float("-inf")

    def report(done: int, total: int) -> None:
        nonlocal last
        with lock:  # the download reports from several threads
            if time.perf_counter() - last >= every or done >= total:
                last = time.perf_counter()
                startup.write(path, model="downloading", done=done, total=total, **status)

    return report
