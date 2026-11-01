"""Run the same recordings through each speech engine, to see which one hears best.

Start Ghostwriter with GHOSTWRITER_KEEP_RECORDINGS set so it saves each dictation in recordings\, dictate, then run:

    .venv\Scripts\python scripts\compare_engines.py

It uses every recording in recordings\ (or just the files named after it) with your dictionary, shows each engine's
text and where it differs from faster-whisper's, and saves the same report as recordings\comparison.txt.
"""

import difflib
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from faster_whisper import decode_audio  # noqa: E402

from ghostwriter.audio import SAMPLE_RATE  # noqa: E402
from ghostwriter.dictionary import DictionaryFile  # noqa: E402
from ghostwriter.models import WHISPER_CPP_COMPRESSED, WHISPER_CPP_FULL  # noqa: E402
from ghostwriter.paths import RECORDINGS_DIR  # noqa: E402
from ghostwriter.transcriber import Transcriber  # noqa: E402
from ghostwriter.whisper_cpp import WhisperCpp, model_paths  # noqa: E402

BASELINE = "faster-whisper"

# Loaded one at a time, so only one sits on the graphics card.
ENGINES = {
    BASELINE: Transcriber,
    "whisper.cpp compressed": lambda: WhisperCpp(*model_paths(WHISPER_CPP_COMPRESSED)),
    "whisper.cpp full size": lambda: WhisperCpp(*model_paths(WHISPER_CPP_FULL)),
}


def differences(baseline: str, text: str) -> list[str]:
    """Each stretch of words where text differs from the baseline, like "we reward -> re-reward"."""
    before, after = baseline.split(), text.split()
    return [f"{' '.join(before[a1:a2]) or '(nothing)'} -> {' '.join(after[b1:b2]) or '(nothing)'}"
            for tag, a1, a2, b1, b2 in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes()
            if tag != "equal"]


def main() -> None:
    files = [Path(name) for name in sys.argv[1:]] or sorted(RECORDINGS_DIR.glob("*.wav"))
    if not files:
        sys.exit(f"No recordings in {RECORDINGS_DIR}. Start Ghostwriter with GHOSTWRITER_KEEP_RECORDINGS set and dictate.")
    dictionary = DictionaryFile().current()
    clips = {path.name: decode_audio(str(path), sampling_rate=SAMPLE_RATE) for path in files}
    results = {}
    for name, load in ENGINES.items():
        print(f"Running {name}...", flush=True)
        engine = load()
        engine.warm_up()
        for clip, audio in clips.items():
            started = time.perf_counter()
            text = dictionary.apply(engine.transcribe(audio, prompt=dictionary.prompt))
            results[clip, name] = text, time.perf_counter() - started
        engine.close()

    report = []
    for clip, audio in clips.items():
        report.append(f"\n== {clip} ({len(audio) / SAMPLE_RATE:.1f} s of audio)")
        baseline = results[clip, BASELINE][0]
        for name in ENGINES:
            text, seconds = results[clip, name]
            report.append(f"\n{name}, {seconds:.2f} s:\n{text}")
            if name != BASELINE:
                changes = differences(baseline, text)
                report.append("  Same words as faster-whisper." if not changes else
                              "  Differs from faster-whisper:\n" + "\n".join(f"    {change}" for change in changes))
    print("\n".join(report))
    RECORDINGS_DIR.mkdir(exist_ok=True)
    (RECORDINGS_DIR / "comparison.txt").write_text("\n".join(report).lstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
