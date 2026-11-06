# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- whisper.cpp builds on Linux with `scripts/build_whisper_cpp.sh`. It includes processor code for every generation of x86 processor and picks the best one at startup, so it also runs on budget chips without AVX.
- The hotkey works on Linux. Ghostwriter reads presses and releases straight from every keyboard, including ones plugged in or paired later, so it works on any desktop. It needs the user in the `input` group, and says so if they aren't. Keyboard layouts where Right Alt is AltGr get Right Ctrl by default, like on Windows.
- Pasting works on Linux with Hyprland. Hyprland presses Ctrl+V, or Ctrl+Shift+V in terminals, so it works in every app, older X11 ones like games included. The dictated text stays out of clipboard history, and the old clipboard comes back afterward (images included; formatted text comes back as plain text).
- History on Linux names the app each dictation went into, from the app's launcher entry. Web apps get their own name (WhatsApp, not Chromium), and Steam games their title.

### Changed
- The Windows-only code now lives in its own folder (`ghostwriter/windows`), and `ghostwriter/system.py` picks the right code for the system Ghostwriter runs on. This gets Ghostwriter ready for Linux; nothing works differently on Windows.

## [1.5.0] - 2026-10-31

Ghostwriter runs on any graphics card now, not just NVIDIA.

### Added
- Ghostwriter now runs on AMD and Intel graphics cards, and on graphics built into the processor, through whisper.cpp and Vulkan. It's about as accurate as the NVIDIA engine, and on an RTX 4090 just as fast.
- On PCs with an NVIDIA card, Settings can switch between faster-whisper and whisper.cpp while Ghostwriter runs. The first switch downloads whisper.cpp's model and shows the progress.
- NVIDIA cards run whisper.cpp with the full-size model (1.6 GB), which matched faster-whisper almost word for word on the same recordings. Other graphics use the compressed model (0.6 GB), which is smaller and faster on chips built into the processor.
- whisper.cpp picks a real graphics card over a chip built into the processor when a PC has both.

### Changed
- The installer no longer turns away PCs without an NVIDIA card. Those PCs skip the 1.3 GB of NVIDIA-only files, so the whole install is about 1 GB.

## [1.4.0] - 2026-10-30

Pick your sounds, hide the pill, test your mic, and start with Windows.

### Added
- Six sound styles to pick from in Settings: Soft (the original), Glass, Bubble, Wood, Tap, and Chime. Picking one plays it.
- The listening pill can be turned off in Settings.
- Start with Windows: Ghostwriter waits in the tray when you log in.
- A mic test in Settings with a live level meter. It closes the mic by itself after 20 seconds or when you leave Settings.

### Changed
- Settings is laid out like the design: Feedback holds the sounds and the pill, and a new General card holds Start with Windows, history, and the file buttons. Open dictionary.txt moved to Edit as text on the Dictionary page.

## [1.3.0] - 2026-10-30

Ghostwriter gets a window: Home, History, Dictionary, and Settings in dark and light, plus a welcome for new installs.

### Added
- The Ghostwriter window, in dark and light: Home with your hotkey, a box to try dictating, and quick switches; a Dictionary page to add and remove words and fixes; and Settings for the hotkey, hands free, microphone, theme, sounds, and files. Check for updates sits at the bottom of the sidebar.
- Starting Ghostwriter opens the window; closing it keeps Ghostwriter running in the tray. Click the ghost, or start it again from the Start menu, to bring the window back. `--tray` starts it without the window.
- The Dictionary page explains the difference: a word is a hint Whisper gets before it listens; a fix swaps what it heard for what you want, every time.
- Hands free can be turned off, and its time limit set to 5, 15, or 30 minutes.
- Settings changed in the window apply right away to the running app.
- History: every dictation is saved on this PC, with the time, how long you talked, and the app it went to. The History page groups them by day, searches them, filters by your most used apps, and copies any of them. New dictations show up while the window is open.
- Home shows today's words and dictations, this month's words, and your three latest dictations.
- Saving history can be turned off in Settings, and Clear history deletes everything saved.
- A dictation is saved to History even if pasting it fails, so the words aren't lost.
- A welcome on the first start: the speech model download with a progress bar and the time left, then picking your hotkey, then trying it out. If the download stops, it says so and picks up where it left off next time.

### Changed
- Starting Ghostwriter while it's already running opens the window instead of showing an "already running" message.

## [1.2.1] - 2026-10-25

### Changed
- The README, starter dictionary, and tests use generic examples (like "my sequel" to "MySQL") instead of my own words.

## [1.2.0] - 2026-10-25

Public release: install or update with one line in PowerShell.

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
- The hotkey is hidden from other apps, and works inside games (tested in a game's chat).
- `dictionary.txt` for names and terms to spell right, plus fixes for things Whisper mishears (like "my sequel" to "MySQL"). Edits apply without a restart.
- A ghost in the system tray that turns red while listening.
- A listening pill at the bottom of the screen with a live mic level, typing dots, and a stop square in lock mode. It never takes focus and lets clicks through.
- Soft start and stop sounds.
- Tray settings for the hotkey, microphone, and sounds, saved to `settings.json`, plus shortcuts to edit the dictionary and open the log.
- A Start menu shortcut that runs Ghostwriter with no terminal window, with its own ghost icon.
- A log at `logs/ghostwriter.log`, one copy running at a time, and an error message if it can't start.
- Tests for the clipboard, hotkey, mic, dictionary, lock mode, settings, and the full dictation loop.

[Unreleased]: https://github.com/Vultify/ghostwriter/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/Vultify/ghostwriter/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/Vultify/ghostwriter/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/Vultify/ghostwriter/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/Vultify/ghostwriter/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/Vultify/ghostwriter/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Vultify/ghostwriter/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Vultify/ghostwriter/releases/tag/v1.0.0
