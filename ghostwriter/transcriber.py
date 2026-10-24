"""Whisper speech to text on the GPU, kept loaded so each dictation starts instantly."""

import os
import site
from pathlib import Path

import numpy as np

MODEL_NAME = "large-v3-turbo"
SAMPLE_RATE = 16000


def _add_cuda_dll_dirs() -> None:
    """Let ctranslate2 find the cuBLAS and cuDNN DLLs that ship inside the nvidia pip packages."""
    for packages_dir in site.getsitepackages():
        for lib in ("cublas", "cudnn", "cuda_nvrtc"):
            bin_dir = Path(packages_dir) / "nvidia" / lib / "bin"
            if bin_dir.is_dir():
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


_add_cuda_dll_dirs()

from faster_whisper import WhisperModel  # noqa: E402  (needs the DLL paths above)


class Transcriber:
    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self.model = WhisperModel(model_name, device="cuda", compute_type="float16")

    def transcribe(self, audio: np.ndarray | str, prompt: str | None = None) -> str:
        """Turn 16 kHz mono float32 audio (or a file path) into text."""
        segments, _ = self.model.transcribe(
            audio,
            language="en",
            beam_size=5,
            vad_filter=True,
            initial_prompt=prompt,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
