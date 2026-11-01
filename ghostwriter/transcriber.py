"""Whisper speech to text with faster-whisper on an NVIDIA GPU, kept loaded so each dictation starts instantly."""

import os
import site
from pathlib import Path

import numpy as np

from ghostwriter.audio import SAMPLE_RATE
from ghostwriter.models import FASTER_WHISPER_FILES, FASTER_WHISPER_REPO, DownloadProgress, fetch

# Whisper follows only its single best guess; weighing 5 was 20% slower and gave the same text in testing.
BEAM_SIZE = 1


def _add_cuda_dll_dirs() -> None:
    """Let ctranslate2 find the cuBLAS and cuDNN DLLs that ship inside the nvidia pip packages."""
    for packages_dir in site.getsitepackages():
        for lib in ("cublas", "cudnn", "cuda_nvrtc"):
            bin_dir = Path(packages_dir) / "nvidia" / lib / "bin"
            if bin_dir.is_dir():
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


_add_cuda_dll_dirs()

import ctranslate2  # noqa: E402  (needs the DLL paths above)
from faster_whisper import WhisperModel  # noqa: E402


def gpu_available() -> bool:
    """Whether there's an NVIDIA GPU that faster-whisper can run on."""
    try:
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def model_path(on_progress: DownloadProgress = lambda done, total: None) -> str:
    return fetch(FASTER_WHISPER_REPO, FASTER_WHISPER_FILES, on_progress)


class Transcriber:
    def __init__(self, path: str | None = None) -> None:
        self.model = WhisperModel(path or model_path(), device="cuda", compute_type="float16")

    def transcribe(self, audio: np.ndarray | str, prompt: str | None = None) -> str:
        """Turn 16 kHz mono float32 audio (or a file path) into text."""
        segments, _ = self.model.transcribe(
            audio,
            language="en",
            beam_size=BEAM_SIZE,
            vad_filter=True,
            initial_prompt=prompt,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def warm_up(self) -> None:
        """Run one throwaway pass so the first real dictation doesn't pay the GPU startup cost."""
        noise = np.random.default_rng(0).normal(0, 0.01, SAMPLE_RATE).astype(np.float32)
        segments, _ = self.model.transcribe(noise, language="en", beam_size=BEAM_SIZE)
        list(segments)  # segments are generated lazily; this forces the pass to run

    def close(self) -> None:
        """Free the GPU memory, when switching to the other engine."""
        self.model = None
