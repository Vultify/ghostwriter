# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- One-line install and update: `irm https://raw.githubusercontent.com/Vultify/ghostwriter/main/get.ps1 | iex` in PowerShell. Updates keep your dictionary, settings, and log.
- **Check for updates** in the tray menu. It asks before updating, then closes Ghostwriter, updates it, and starts it again.

### Changed
- The starter dictionary now has common app names (GitHub, VS Code, Discord, and more), which also helps Whisper capitalize them, plus examples of adding your own words and fixes.
- `install.bat` can run without questions (`install.bat /quiet`) and reports whether it worked.

## [1.1.0] - 2026-10-25

Ready to share: anyone with an NVIDIA graphics card can download the ZIP and install Ghostwriter with a double click.

### Added
- `install.bat`: download the ZIP, double click it, and Ghostwriter installs its own Python and packages inside its folder and adds itself to the Start menu. Safe to run again.
- A notification while the speech model downloads on first start, and another when it's ready.
- A clear message on PCs without an NVIDIA graphics card, instead of a crash.

### Changed
- The default hotkey is Right Ctrl on keyboards where Right Alt is AltGr, so it doesn't block typing characters like @ and €.
- `dictionary.txt` is now personal and no longer in git. New installs start from `dictionary.example.txt`.

## [1.0.0] - 2026-10-25

The first release: local, unlimited dictation that replaces Wispr Flow for my daily use.

### Added
- Hold to talk: hold Right Alt, talk, and let go to paste the text where the cursor is.
- Lock mode: double tap Right Alt to record hands free, tap again to stop. Recording stops by itself after 15 minutes in case it's left on.
- Speech to text with Whisper large-v3-turbo on the GPU, kept loaded so each dictation takes a fraction of a second. After the first download it never goes online.
- Fast finish: recording ends as soon as you go quiet after letting go, so the text usually lands within about 0.2 seconds on the desktop.
- Pasting through the clipboard and Ctrl+V, with your clipboard put back right after and dictations kept out of Win+V history.
- The hotkey is hidden from other apps, and works inside games (tested in Wardogs chat).
- `dictionary.txt` for names and terms to spell right, plus fixes for things Whisper mishears (like "sea whiz" to "CIWS"). Edits apply without a restart.
- A ghost in the system tray that turns red while listening.
- A listening pill at the bottom of the screen with a live mic level, typing dots, and a stop square in lock mode. It never takes focus and lets clicks through.
- Soft start and stop sounds.
- Tray settings for the hotkey, microphone, and sounds, saved to `settings.json`, plus shortcuts to edit the dictionary and open the log.
- A Start menu shortcut that runs Ghostwriter with no terminal window, with its own ghost icon.
- A log at `logs/ghostwriter.log`, one copy running at a time, and an error message if it can't start.
- Tests for the clipboard, hotkey, mic, dictionary, lock mode, settings, and the full dictation loop.

[Unreleased]: https://github.com/Vultify/ghostwriter/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/Vultify/ghostwriter/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Vultify/ghostwriter/releases/tag/v1.0.0
