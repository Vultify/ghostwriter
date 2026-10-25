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
- `dictionary.txt` for words to spell right and fixes for things Whisper mishears (like "sea whiz" to "CIWS"). Edits apply without a restart.
- Lock mode: double tap Right Alt to record hands free, tap again to stop. The pill shows a stop square while locked, and recording stops by itself after 15 minutes.

- Settings in the tray menu: hotkey, microphone, and sounds, saved to `settings.json` and applied right away.
- Tray menu items to edit the dictionary and open the log.
- Runs with no terminal window from a Start menu shortcut (`scripts/make_shortcut.py`), with its own ghost app icon.
- Log file at `logs/ghostwriter.log`, including which app each dictation was pasted into.
- Only one copy of Ghostwriter runs at a time.
- An error message box if Ghostwriter can't start, instead of quietly closing.

### Changed
- Faster paste after you let go: recording ends as soon as you've gone quiet (about 0.08s instead of a fixed 0.3s), and Whisper follows its single best guess instead of weighing five (about 20% faster, same text in testing).
- A lone quick tap (under 0.3 seconds) now waits briefly for a second tap before it's thrown away.
- Softer, lower start and stop sounds: a quick "bloop" that settles up onto C to start, and slides down to stop.
- The tray ghost appears right away while Whisper loads.
