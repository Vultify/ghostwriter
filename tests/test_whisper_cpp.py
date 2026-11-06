"""whisper.cpp, the speech engine for graphics cards that aren't NVIDIA: picking the graphics, transcribing, closing
with Ghostwriter, and switching engines while Ghostwriter runs."""

import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
from conftest import fixed_dictionary, speak_to_wav
from faster_whisper import decode_audio

from ghostwriter import models, speech, startup
from ghostwriter.audio import SAMPLE_RATE
from ghostwriter.paths import PROJECT
from ghostwriter.speech import SpeechEngine
from ghostwriter.transcriber import gpu_available
from ghostwriter.whisper_cpp import WhisperCpp, model_paths, pick_device

NVIDIA = "ggml_vulkan: {} = NVIDIA GeForce RTX 4090 (NVIDIA) | uma: 0 | fp16: 1 | warp size: 32"
INTEL = "ggml_vulkan: {} = Intel(R) UHD Graphics 770 (Intel Corporation) | uma: 1 | fp16: 1 | warp size: 32"
needs_whisper_cpp = pytest.mark.skipif(not (models.whisper_cpp_installed() and models.downloaded(models.WHISPER_CPP, has_nvidia=False)),
                                       reason="whisper.cpp or its model isn't on this PC")


def test_a_real_graphics_card_wins_over_a_built_in_chip():
    log = "ggml_vulkan: Found 2 Vulkan devices:\n" + INTEL.format(0) + "\n" + NVIDIA.format(1)
    assert pick_device(log) == (1, "NVIDIA GeForce RTX 4090")
    assert pick_device(NVIDIA.format(0) + "\n" + INTEL.format(1)) == (0, "NVIDIA GeForce RTX 4090")
    assert pick_device(INTEL.format(0)) == (0, "Intel(R) UHD Graphics 770")
    assert pick_device("whisper_backend_init_gpu: no GPU found") is None


def test_each_pc_gets_an_engine_it_can_run(monkeypatch):
    monkeypatch.setattr(models, "whisper_cpp_installed", lambda: True)
    assert models.resolve("auto", has_nvidia=True) == models.FASTER_WHISPER
    assert models.resolve("whisper.cpp", has_nvidia=True) == models.WHISPER_CPP
    assert models.resolve("auto", has_nvidia=False) == models.WHISPER_CPP
    assert models.resolve("faster-whisper", has_nvidia=False) == models.WHISPER_CPP  # no NVIDIA card to run it
    monkeypatch.setattr(models, "whisper_cpp_installed", lambda: False)
    assert models.resolve("whisper.cpp", has_nvidia=True) == models.FASTER_WHISPER  # not installed yet
    assert models.available(has_nvidia=False) == []


def test_nvidia_cards_get_the_full_size_whisper_cpp_model_and_others_the_compressed_one():
    assert models.whisper_cpp_model(has_nvidia=True) == models.WHISPER_CPP_FULL
    assert models.whisper_cpp_model(has_nvidia=False) == models.WHISPER_CPP_COMPRESSED
    assert models.size(models.WHISPER_CPP, has_nvidia=True) == models.size(models.FASTER_WHISPER, has_nvidia=True) == "1.6 GB"
    assert models.size(models.WHISPER_CPP, has_nvidia=False) == "0.6 GB"


@pytest.fixture(scope="module")
def spoken():
    clip = Path(tempfile.gettempdir()) / "ghostwriter_whisper_cpp_test.wav"
    speak_to_wav("Deploy the my sequel backup tonight and send the link to Brightwater Detailing.", clip)
    audio = decode_audio(str(clip), sampling_rate=SAMPLE_RATE)
    clip.unlink(missing_ok=True)
    return audio


@needs_whisper_cpp
def test_whisper_cpp_transcribes_with_the_word_list_and_closes(spoken):
    engine = WhisperCpp(*model_paths(models.WHISPER_CPP_COMPRESSED))
    try:
        dictionary = fixed_dictionary().current()
        engine.warm_up()
        text = dictionary.apply(engine.transcribe(spoken, prompt=dictionary.prompt))
        server = engine._server
    finally:
        engine.close()
    assert text == "Deploy the MySQL backup tonight and send the link to Brightwater Detailing."
    assert engine.device != "the processor"
    assert server.poll() is not None


@needs_whisper_cpp
def test_the_server_closes_when_ghostwriter_is_killed():
    """Even a crash or a forced quit takes whisper.cpp down with it, so it never sits in graphics memory."""
    script = ("import sys, time; sys.path.insert(0, r'%s'); from ghostwriter.whisper_cpp import WhisperCpp, "
              "model_paths; engine = WhisperCpp(*model_paths('%s')); print(engine._server.pid, flush=True); "
              "time.sleep(60)") % (PROJECT, models.WHISPER_CPP_COMPRESSED)
    owner = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True)
    server = int(owner.stdout.readline())
    owner.kill()  # a forced quit: TerminateProcess on Windows, SIGKILL on Linux
    owner.wait()
    deadline = time.perf_counter() + 10
    while time.perf_counter() < deadline and _running(server):
        time.sleep(0.2)
    assert not _running(server)


def _running(process_id: int) -> bool:
    if sys.platform != "win32":
        try:
            state = Path(f"/proc/{process_id}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except FileNotFoundError:
            return False
        return state != "Z"  # a finished program waiting to be cleaned up counts as gone
    found = subprocess.run(["tasklist", "/FI", f"PID eq {process_id}", "/NH"], capture_output=True, text=True).stdout
    return str(process_id) in found


class FakeEngine:
    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False

    def transcribe(self, audio, prompt=None) -> str:
        return self.name

    def close(self) -> None:
        self.closed = True


def _wait_for(check, timeout: float = 5.0) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline and not check():
        time.sleep(0.02)


def test_switching_engines_keeps_dictating_and_closes_the_old_one(monkeypatch, tmp_path):
    monkeypatch.setattr(speech.startup, "write", lambda *args, **status: None)
    loading = threading.Event()

    def load_engine(name, has_nvidia, first_run=False, path=None):
        if name == models.WHISPER_CPP:
            loading.wait(5)  # a slow download
        return FakeEngine(name)

    monkeypatch.setattr(speech, "load_engine", load_engine)
    engine = SpeechEngine(has_nvidia=True)
    engine.load(models.FASTER_WHISPER)
    first = engine._engine
    engine.switch_to(models.WHISPER_CPP)
    assert engine.transcribe(None) == models.FASTER_WHISPER  # still dictating while the other one loads
    loading.set()
    _wait_for(lambda: engine.name == models.WHISPER_CPP)
    assert engine.transcribe(None) == models.WHISPER_CPP
    assert first.closed


def test_an_engine_that_fails_to_load_leaves_the_old_one_running(monkeypatch):
    monkeypatch.setattr(speech.startup, "write", lambda *args, **status: None)
    attempts = []

    def load_engine(name, has_nvidia, first_run=False, path=None):
        attempts.append(name)
        if name == models.WHISPER_CPP:
            raise OSError("no internet")
        return FakeEngine(name)

    monkeypatch.setattr(speech, "load_engine", load_engine)
    engine = SpeechEngine(has_nvidia=True)
    engine.load(models.FASTER_WHISPER)
    engine.switch_to(models.WHISPER_CPP)
    _wait_for(lambda: not engine._switching)
    engine.switch_to(models.WHISPER_CPP)  # another settings change doesn't retry the download
    time.sleep(0.2)
    assert engine.name == models.FASTER_WHISPER and engine.transcribe(None) == models.FASTER_WHISPER
    assert attempts == [models.FASTER_WHISPER, models.WHISPER_CPP]
    engine.switch_to(models.FASTER_WHISPER)  # picking it again later does retry
    engine.switch_to(models.WHISPER_CPP)
    _wait_for(lambda: not engine._switching)
    assert attempts.count(models.WHISPER_CPP) == 2


@needs_whisper_cpp
@pytest.mark.skipif(not gpu_available(), reason="switching needs faster-whisper, which needs an NVIDIA card")
def test_switching_real_engines_back_and_forth(spoken, tmp_path):
    status = tmp_path / "startup.json"
    engine = SpeechEngine(has_nvidia=False, status_path=status)
    dictionary = fixed_dictionary().current()
    heard, reported = [], []
    try:
        engine.load(models.FASTER_WHISPER)
        heard.append(dictionary.apply(engine.transcribe(spoken, prompt=dictionary.prompt)))
        for target in (models.WHISPER_CPP, models.FASTER_WHISPER):
            engine.switch_to(target)
            _wait_for(lambda: engine.name == target and not engine._switching, timeout=60)
            heard.append(dictionary.apply(engine.transcribe(spoken, prompt=dictionary.prompt)))
            reported.append((startup.read(status)["engine"], startup.read(status)["model"]))
    finally:
        engine.close()
    assert heard == ["Deploy the MySQL backup tonight and send the link to Brightwater Detailing."] * 3
    assert reported == [(models.WHISPER_CPP, "ready"), (models.FASTER_WHISPER, "ready")]
