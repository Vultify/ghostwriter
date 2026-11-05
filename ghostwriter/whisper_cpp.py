"""Whisper speech to text with whisper.cpp, which runs on any graphics card through Vulkan.

whisper.cpp runs as its own small server program (whisper-server in .whisper-cpp, built by
scripts/build_whisper_cpp.ps1 on Windows) that keeps the model loaded on the graphics card, and each dictation is
sent to it over a connection that never leaves this PC. The server is tied to Ghostwriter, so it closes when
Ghostwriter does, even after a crash.
"""

import json
import logging
import re
import socket
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path

import numpy as np

from ghostwriter.audio import SAMPLE_RATE, wav_bytes
from ghostwriter.models import VAD_MODEL, VAD_REPO, WHISPER_CPP_REPO, DownloadProgress, fetch
from ghostwriter.paths import LOG_DIR, WHISPER_SERVER as SERVER
from ghostwriter.system import processes

SERVER_LOG = LOG_DIR / "whisper-cpp.log"
START_SECONDS = 90  # loading the model onto a slow graphics chip can take a while
REQUEST_SECONDS = 120

# One line per graphics device the server finds, like "ggml_vulkan: 0 = NVIDIA GeForce RTX 4090 (NVIDIA) | uma: 0 |".
# uma 1 means the graphics share the processor's memory: a chip built into the processor, slower than a real card.
_DEVICE_LINE = re.compile(r"ggml_vulkan: (\d+) = (.+?) \([^)]*\) \| uma: (\d)")

log = logging.getLogger("ghostwriter")


class WhisperCppError(RuntimeError):
    pass


def model_paths(model_file: str, on_progress: DownloadProgress = lambda done, total: None) -> tuple[Path, Path]:
    """A speech model (models.whisper_cpp_model picks which) and the silence detector, downloaded on first use."""
    vad = Path(fetch(VAD_REPO, [VAD_MODEL])) / VAD_MODEL
    model = Path(fetch(WHISPER_CPP_REPO, [model_file], on_progress)) / model_file
    return model, vad


def pick_device(server_log: str) -> tuple[int, str] | None:
    """The best graphics device the server found: a real graphics card before one built into the processor."""
    devices = [(int(index), name, uma == "1") for index, name, uma in _DEVICE_LINE.findall(server_log)]
    if not devices:
        return None
    index, name, _ = min(devices, key=lambda device: (device[2], device[0]))
    return index, name


class WhisperCpp:
    def __init__(self, model: Path, vad: Path) -> None:
        self.model = model
        self.vad = vad
        self.device = "the processor"  # until the server says which graphics it found
        self._device_index: int | None = None
        self._children = processes.Children()
        self._server: subprocess.Popen | None = None
        self._port = 0
        self._lock = threading.Lock()
        self._start()
        found = pick_device(SERVER_LOG.read_text(encoding="utf-8", errors="replace"))
        if found is None:
            log.warning("whisper.cpp found no Vulkan graphics, so it's running on the processor, which is slow")
            return
        self._device_index, self.device = found
        if self._device_index != 0:  # the server loaded onto a built-in chip first; move it to the real card
            self._stop()
            self._start()
        log.info("whisper.cpp is running on %s", self.device)

    def transcribe(self, audio: np.ndarray, prompt: str | None = None) -> str:
        """Turn 16 kHz mono float32 audio into text."""
        with self._lock:
            if self._server.poll() is not None:
                log.warning("whisper.cpp had stopped, so it's starting again")
                self._start()
            fields = {"language": "en", "temperature": "0", "response_format": "json", "vad": "true"}
            if prompt:
                fields["prompt"] = prompt
            reply = self._post(fields, wav_bytes(audio))
        if "error" in reply:
            raise WhisperCppError(f"whisper.cpp couldn't transcribe: {reply['error']}")
        return " ".join(reply.get("text", "").split())

    def warm_up(self) -> None:
        """Run one throwaway pass so the first real dictation doesn't pay the graphics card's startup cost."""
        self.transcribe(np.random.default_rng(0).normal(0, 0.01, SAMPLE_RATE).astype(np.float32))

    def close(self) -> None:
        with self._lock:
            self._stop()
            self._children.close()

    def _start(self) -> None:
        self._port = _free_port()
        args = [str(SERVER), "-m", str(self.model), "-vm", str(self.vad), "--host", "127.0.0.1",
                "--port", str(self._port), "-l", "en", "-fa"]
        if self._device_index is not None:
            args += ["-dev", str(self._device_index)]
        SERVER_LOG.parent.mkdir(exist_ok=True)
        with open(SERVER_LOG, "w", encoding="utf-8") as output:
            self._server = self._children.start(args, stdin=subprocess.DEVNULL, stdout=output,
                                                stderr=subprocess.STDOUT)
        deadline = time.perf_counter() + START_SECONDS
        while not self._answers():
            if self._server.poll() is not None:
                raise WhisperCppError(f"whisper.cpp stopped while starting. Details are in {SERVER_LOG}")
            if time.perf_counter() > deadline:
                self._stop()
                raise WhisperCppError(f"whisper.cpp took over {START_SECONDS} seconds to start")
            time.sleep(0.1)

    def _stop(self) -> None:
        if self._server and self._server.poll() is None:
            self._server.terminate()
            self._server.wait(timeout=10)

    def _answers(self) -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self._port}/", timeout=1):
                return True
        except OSError:
            return False

    def _post(self, fields: dict[str, str], audio: bytes) -> dict:
        boundary = uuid.uuid4().hex
        parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
                 for name, value in fields.items()]
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="dictation.wav"\r\n'
                     "Content-Type: audio/wav\r\n\r\n".encode() + audio + b"\r\n")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self._port}/inference", data=b"".join(parts) + f"--{boundary}--\r\n".encode(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(request, timeout=REQUEST_SECONDS) as response:
            return json.loads(response.read())


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]

