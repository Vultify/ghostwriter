"""Soft sounds for when Ghostwriter starts and stops listening (made by scripts/make_sounds.py)."""

import winsound
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"
_FLAGS = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT


def play_start() -> None:
    winsound.PlaySound(str(ASSETS / "start.wav"), _FLAGS)


def play_stop() -> None:
    winsound.PlaySound(str(ASSETS / "stop.wav"), _FLAGS)
