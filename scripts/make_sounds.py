"""Make Ghostwriter's start and stop sounds: short, soft blips that glide up to start and down to stop."""

import wave
from pathlib import Path

import numpy as np

RATE = 44100
ASSETS = Path(__file__).resolve().parent.parent / "ghostwriter" / "assets"


def blip(start_hz: float, end_hz: float, seconds: float = 0.09, volume: float = 0.22) -> np.ndarray:
    t = np.arange(int(RATE * seconds)) / RATE
    phase = 2 * np.pi * np.cumsum(np.geomspace(start_hz, end_hz, len(t))) / RATE
    tone = (np.sin(phase) + 0.25 * np.sin(2 * phase)) / 1.25  # a touch of overtone so it isn't a pure beep
    envelope = np.minimum(1, t / 0.004) * np.exp(-t / 0.03)  # 4 ms fade in, quick decay
    return volume * tone * envelope


def save(name: str, samples: np.ndarray) -> None:
    with wave.open(str(ASSETS / f"{name}.wav"), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(RATE)
        file.writeframes((samples * 32767).astype("<i2").tobytes())


if __name__ == "__main__":
    ASSETS.mkdir(exist_ok=True)
    save("start", blip(700, 1050))
    save("stop", blip(1050, 700))
    print(f"Saved start.wav and stop.wav to {ASSETS}")
