"""The two speech engines and where their models come from, kept light so the app window can ask without loading
either engine.

faster-whisper runs on NVIDIA cards through CUDA. whisper.cpp runs on any graphics card through Vulkan (AMD, Intel,
and NVIDIA too), so it's what PCs without an NVIDIA card use.
"""

from collections.abc import Callable

from huggingface_hub import snapshot_download, try_to_load_from_cache
from huggingface_hub.utils import tqdm as hf_tqdm

from ghostwriter.paths import WHISPER_SERVER

DownloadProgress = Callable[[int, int], None]  # bytes downloaded so far, and the total

FASTER_WHISPER = "faster-whisper"
WHISPER_CPP = "whisper.cpp"
ENGINES = (FASTER_WHISPER, WHISPER_CPP)
ENGINE_SETTINGS = ("auto", *ENGINES)  # auto: faster-whisper on NVIDIA cards, whisper.cpp everywhere else

# Whisper large-v3-turbo in each engine's format. whisper.cpp comes full size and compressed (q5_0).
FASTER_WHISPER_REPO = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
FASTER_WHISPER_FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]
WHISPER_CPP_REPO = "ggerganov/whisper.cpp"
WHISPER_CPP_FULL = "ggml-large-v3-turbo.bin"
WHISPER_CPP_COMPRESSED = "ggml-large-v3-turbo-q5_0.bin"
VAD_REPO = "ggml-org/whisper-vad"
VAD_MODEL = "ggml-silero-v5.1.2.bin"  # skips silence, like faster-whisper's built in filter


def whisper_cpp_model(has_nvidia: bool) -> str:
    """NVIDIA cards have the memory for the full model, which came closest to faster-whisper in Caleb's test. Other
    graphics get the compressed one: a third of the download, and faster on chips built into the processor."""
    return WHISPER_CPP_FULL if has_nvidia else WHISPER_CPP_COMPRESSED


def size(engine: str, has_nvidia: bool) -> str:
    return "0.6 GB" if engine == WHISPER_CPP and not has_nvidia else "1.6 GB"


def whisper_cpp_installed() -> bool:
    return WHISPER_SERVER.exists()


def available(has_nvidia: bool) -> list[str]:
    """The engines this PC can run."""
    return [engine for engine, usable in ((FASTER_WHISPER, has_nvidia), (WHISPER_CPP, whisper_cpp_installed()))
            if usable]


def resolve(setting: str, has_nvidia: bool) -> str:
    """The engine a setting means on this PC: the one picked if it can run here, otherwise the best one that can."""
    usable = available(has_nvidia)
    if setting in usable:
        return setting
    return FASTER_WHISPER if FASTER_WHISPER in usable else WHISPER_CPP


def downloaded(engine: str, has_nvidia: bool) -> bool:
    if engine == FASTER_WHISPER:
        return isinstance(try_to_load_from_cache(FASTER_WHISPER_REPO, "model.bin"), str)
    return all(isinstance(try_to_load_from_cache(repo, name), str)
               for repo, name in ((WHISPER_CPP_REPO, whisper_cpp_model(has_nvidia)), (VAD_REPO, VAD_MODEL)))


def fetch(repo: str, patterns: list[str], on_progress: DownloadProgress = lambda done, total: None) -> str:
    """A model's folder on disk, found offline so startup never goes online. Only its first use downloads it."""
    try:
        return snapshot_download(repo, allow_patterns=patterns, local_files_only=True)
    except Exception:  # not downloaded yet
        return snapshot_download(repo, allow_patterns=patterns, tqdm_class=_progress_bars(on_progress))


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
