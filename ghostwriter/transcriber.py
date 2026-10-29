"""Whisper speech to text on the GPU, kept loaded so each dictation starts instantly."""

import os
import site
from collections.abc import Callable
from pathlib import Path

import numpy as np

from ghostwriter.audio import SAMPLE_RATE

# Whisper large-v3-turbo, converted for faster-whisper, and the files it needs from that repo.
MODEL_REPO = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
MODEL_FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]
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
from huggingface_hub import snapshot_download  # noqa: E402
from huggingface_hub.utils import tqdm as hf_tqdm  # noqa: E402

DownloadProgress = Callable[[int, int], None]  # bytes downloaded so far, and the total


def gpu_available() -> bool:
    """Whether there's an NVIDIA GPU that Whisper can run on."""
    try:
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def model_downloaded() -> bool:
    try:
        snapshot_download(MODEL_REPO, allow_patterns=MODEL_FILES, local_files_only=True)
        return True
    except Exception:
        return False


def model_path(on_progress: DownloadProgress = lambda done, total: None) -> str:
    """Find the model on disk, so startup never goes online. Only the very first run downloads it."""
    try:
        return snapshot_download(MODEL_REPO, allow_patterns=MODEL_FILES, local_files_only=True)
    except Exception:  # not downloaded yet
        return snapshot_download(MODEL_REPO, allow_patterns=MODEL_FILES, tqdm_class=_progress_bars(on_progress))


def _progress_bars(on_progress: DownloadProgress) -> type[hf_tqdm]:
    """Progress bars for the download that pass the byte count to on_progress. The bar for bytes received
    moves steadily; the others count files or only move when a file finishes."""

    class ProgressBar(hf_tqdm):
        def __init__(self, *args, **kwargs) -> None:
            self._counts_bytes = kwargs.get("name") == "huggingface_hub.snapshot_download.transfer"
            self._received = 0
            super().__init__(*args, **kwargs)

        def update(self, n=1):
            if self._counts_bytes and n:
                self._received += n  # counted here because a hidden bar skips its own count
                on_progress(min(self._received, self.total or 0), self.total or 0)
            return super().update(n)

    return ProgressBar


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
