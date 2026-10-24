"""Record a few seconds from the default mic and print what Whisper heard, raw and with the word list."""

import sys
import time
from pathlib import Path

import sounddevice as sd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostwriter.transcriber import SAMPLE_RATE, Transcriber  # noqa: E402

SECONDS = 8
VOCABULARY = "Ghostwriter, Tulare, Castro Detailing, Supabase, Claude Code."


def main() -> None:
    transcriber = Transcriber()
    print(f"Mic: {sd.query_devices(kind='input')['name']}")
    input(f"Press Enter, then talk for {SECONDS} seconds...")
    print("Recording...")
    audio = sd.rec(SECONDS * SAMPLE_RATE, samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    audio = audio.flatten()

    start = time.perf_counter()
    raw = transcriber.transcribe(audio)
    elapsed = time.perf_counter() - start
    print(f"Raw:       {raw}")
    print(f"With list: {transcriber.transcribe(audio, prompt=VOCABULARY)}")
    print(f"Took {elapsed:.2f}s")


if __name__ == "__main__":
    main()
