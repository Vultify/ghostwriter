"""Checkpoint 1: make a spoken test clip with the Windows voice, transcribe it, and time it."""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostwriter.transcriber import Transcriber  # noqa: E402

SENTENCE = "Hey, this is a quick test of Ghostwriter. Book the ceramic coating for Friday morning in Tulare."
TARGET_SECONDS = 0.5
VOCABULARY = "Ghostwriter, Tulare, Castro Detailing."


def speak_to_wav(text: str, path: Path) -> None:
    """Use the built-in Windows speech voice to save the sentence as a 16 kHz WAV."""
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, 'Sixteen', 'Mono');"
        f"$s.SetOutputToWaveFile('{path}', $f);"
        f"$s.Speak('{text}');"
        "$s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


def main() -> int:
    clip = Path(tempfile.gettempdir()) / "ghostwriter_smoke.wav"
    speak_to_wav(SENTENCE, clip)

    start = time.perf_counter()
    transcriber = Transcriber()
    print(f"Model loaded in {time.perf_counter() - start:.1f}s")

    transcriber.transcribe(str(clip))  # first pass warms up the GPU

    start = time.perf_counter()
    raw = transcriber.transcribe(str(clip))
    elapsed = time.perf_counter() - start
    with_vocab = transcriber.transcribe(str(clip), prompt=VOCABULARY)
    clip.unlink(missing_ok=True)

    print(f"Expected:        {SENTENCE}")
    print(f"Heard (raw):     {raw}")
    print(f"Heard (w/ list): {with_vocab}")
    print(f"Warm transcription: {elapsed:.2f}s (target under {TARGET_SECONDS}s)")
    passed = elapsed < TARGET_SECONDS and "Ghostwriter" in with_vocab and "Tulare" in with_vocab
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
