# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Project plan, roadmap, and README.
- Whisper large-v3-turbo transcription on the GPU, kept loaded for fast repeat use.
- Speed test and microphone test scripts.
- Hold to talk dictation: hold Right Alt, talk, and let go to paste the text where the cursor is (`python -m ghostwriter`).
- Right Alt is hidden from other apps while Ghostwriter runs.
- The clipboard is put back after each paste, and dictated text stays out of Win+V history.
- The model loads from disk with no network calls after the first download.
- Tests for the clipboard, hotkey, mic, and the full dictation loop.
- Ghost icon in the system tray that turns red while listening, with Quit.
- Listening pill at the bottom center of the screen with a live mic level, then typing dots. It never takes focus and lets clicks through.
- Soft start and stop sounds (`scripts/make_sounds.py` makes them).
- "Wardogs" added to the word list.
