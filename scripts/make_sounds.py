"""Make Ghostwriter's Soft start and stop sounds: low "bloops" that swell in gently and fade fast."""

import wave
from pathlib import Path

import numpy as np

RATE = 44100
ASSETS = Path(__file__).resolve().parent.parent / "ghostwriter" / "assets"
PEAK_DB = -6  # clearly audible over game audio without being harsh


def bloop(start_hz: float, end_hz: float, glide: float, attack: float, decay: float, seconds: float) -> np.ndarray:
    """A short tone that bends from start_hz toward end_hz, rising in over `attack` and dying away over `decay`."""
    t = np.arange(int(RATE * seconds)) / RATE
    frequency = end_hz + (start_hz - end_hz) * np.exp(-t / glide)
    phase = 2 * np.pi * np.cumsum(frequency) / RATE
    # A little second and third harmonic gives it a soft, rounded body instead of a pure beep.
    tone = np.sin(phase) + 0.3 * np.sin(2 * phase) + 0.08 * np.sin(3 * phase)
    rise = np.sin(np.pi / 2 * np.minimum(1, t / attack)) ** 2
    fall = np.exp(-np.maximum(0, t - attack) / decay)
    sound = tone * rise * fall
    sound[-int(RATE * 0.005):] *= np.linspace(1, 0, int(RATE * 0.005))  # no click at the very end
    return sound / np.abs(sound).max() * 10 ** (PEAK_DB / 20)


def save(name: str, samples: np.ndarray) -> None:
    with wave.open(str(ASSETS / f"{name}.wav"), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(RATE)
        file.writeframes((samples * 32767).astype("<i2").tobytes())


if __name__ == "__main__":
    ASSETS.mkdir(exist_ok=True)
    save("soft-start", bloop(start_hz=470, end_hz=523, glide=0.02, attack=0.022, decay=0.009, seconds=0.12))  # settles up onto C
    save("soft-stop", bloop(start_hz=523, end_hz=349, glide=0.035, attack=0.03, decay=0.02, seconds=0.17))  # slides down to F
    print(f"Saved soft-start.wav and soft-stop.wav to {ASSETS}")
