"""The sounds for when Ghostwriter starts and stops listening, in a few styles to pick from in Settings.

Each style is a start and stop WAV in assets. Soft, the default, is made by scripts/make_sounds.py.
"""

import time
from pathlib import Path

from ghostwriter.system import desktop

ASSETS = Path(__file__).resolve().parent / "assets"
STYLES = ("soft", "glass", "bubble", "wood", "tap", "chime")
PREVIEW_PAUSE_SECONDS = 0.35  # between start and stop in a preview, like a very short dictation


def sound_path(style: str, part: str) -> Path:
    return ASSETS / f"{style}-{part}.wav"


def play_start(style: str = "soft") -> None:
    desktop.play_sound(sound_path(style, "start"))


def play_stop(style: str = "soft") -> None:
    desktop.play_sound(sound_path(style, "stop"))


def preview(style: str) -> None:
    """Play a style's start and stop sounds back to back. Returns once both have finished."""
    desktop.play_sound(sound_path(style, "start"), wait=True)
    time.sleep(PREVIEW_PAUSE_SECONDS)
    desktop.play_sound(sound_path(style, "stop"), wait=True)
