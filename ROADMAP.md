# Ghostwriter roadmap

My build order. I check items off as I go.

## Phase 1: foundation
- [x] Python 3.11 kept inside the project (`.python`), venv in `.venv`
- [x] Install faster-whisper with GPU support
- [x] Smoke test: transcribe a short recording on the 4090 and print the time it took (0.16s warm)
- [x] Mic test with my real voice (`scripts/mic_test.py`): 0.40s, every word right with the word list
- **Checkpoint 1 passed 2026-10-23:** my voice comes back as correct text in under half a second

## Phase 2: design
- [x] Pasting: clipboard and Ctrl+V, with the old clipboard put back afterward
- [x] Hotkey: telling a hold from a double tap, and keeping the key away from the app underneath
- [x] Mic: starting fast enough that the first word is not cut off
- [x] Knowing which app is in front
- **Checkpoint 2 passed 2026-10-24:** mic opens on press, single key hotkey, clipboard put back after pasting

## Phase 3: core dictation loop
- [x] Pick a single key hotkey: Right Alt (not Ctrl+Win, that is Wispr; not Ctrl+Alt+J, that is Jarvis)
- [x] Global hotkey: hold to talk, with the key swallowed so the app in front never sees it
- [x] Open the mic on key press and record until release, plus a short tail; measure how fast it opens (first audio in 35 to 55 ms)
- [x] Transcribe with the model kept warm in memory
- [x] Paste the text where the cursor is, then put the old clipboard back
- **Checkpoint 3 passed 2026-10-24:** my dictations landed correctly; mic opens in 10 to 18 ms, transcription takes 0.13 to 0.18s

## Phase 4: tray, indicator, and sound
Moved ahead of lock mode, because lock mode keeps recording after you let go and you need to see that.
- [x] Ghost icon in the system tray that turns red while listening, with Quit
- [x] Listening pill at the bottom center of the screen with a live mic level, then "typing" dots; never takes focus and lets clicks through
- [x] Soft sound when listening starts and stops
- **Checkpoint 4 passed 2026-10-24:** tray ghost, listening pill, and sounds all working

## Phase 5: lock mode
- [x] Double tap the hotkey to keep recording hands free; tap again to stop (tap under 0.3s, second press within 0.4s, 15 minute safety limit)
- [x] Pill shows a stop square and the start sound plays twice while locked
- **Checkpoint 5 passed 2026-10-24:** my 66 second ramble came out complete, transcribed in 0.67s

## Phase 6: custom dictionary
Pulled ahead of lock mode on 2026-10-24 so terms that sound different from how they're spelled come out right.
- [x] `dictionary.txt` of words Whisper should know (names, places, and game terms); edits apply without a restart
- [x] Optional find and replace rules for words it still gets wrong (like `my sequel -> MySQL`)
- **Checkpoint 6 passed 2026-10-24:** every dictionary word comes out right in a spoken test run, and a sound-alike game term came out right in my own voice

## Phase 7: settings and launching
- [x] Settings in the tray menu, saved to `settings.json` (hotkey, mic, sounds), plus Edit dictionary and Open log
- [x] Runs with no console window, logs to `logs/ghostwriter.log`, one copy at a time, error box if it can't start
- [x] Start menu shortcut that launches it with no console window (`scripts/make_shortcut.py`, run by hand so it lands in my real Start menu)
- **Checkpoint 7 passed 2026-10-25:** I used it all day on 2026-10-24, including 13 dictations into a game's chat. Felt a little slow to paste while gaming (transcription ~1s with the game on the GPU, vs ~0.2s on the desktop).

## Speed pass (after Checkpoint 7)
- [x] End recording as soon as I go quiet after letting go (tail ~0.08s, was 0.3s)
- [x] Whisper beam size 5 to 1 (88 ms vs 112 ms per short phrase, same text)
- **Check passed 2026-10-25:** it feels faster even on the desktop; transcription 0.09 to 0.15s, no last words clipped

## Version 1.0.0 released 2026-10-25
Phases 1 to 7 plus the speed pass.

## Ready to share (version 1.1.0, released 2026-10-25)
- [x] `install.bat`: download the ZIP, double click, done (own Python and packages inside the folder, Start menu shortcut)
- [x] Personal `dictionary.txt` out of git; new installs start from `dictionary.example.txt`
- [x] Right Ctrl by default on AltGr keyboards
- [x] Clear message on PCs without an NVIDIA GPU
- [x] Notification during the one time model download

## Going public (version 1.2.0, released 2026-10-25)
- [x] One-line install and update (`get.ps1`), plus Check for updates in the tray
- [x] Starter dictionary with common app names
- [x] Private notes out of the repo
- [x] Clean old private files out of the git history
- [ ] Make the GitHub repo public, then try the one-line install on a second PC

## Phase 8: the app window
Built from my design (dark and light themes, mint accent, Geist font), shown in a real window through the web engine built into Windows (pywebview).
- [x] Window with its own title bar and a sidebar: Home, Dictionary, Settings, the version, and Check for updates (History joins in Phase 9)
- [x] Closing the window keeps Ghostwriter running in the tray; the tray menu gets Open Ghostwriter (also a left click on the ghost)
- [x] Home: ready card showing the hotkey, a box to try dictating, and quick switches
- [x] Settings: hotkey, hands free on/off and its auto-stop time, mic, sounds, speech model info, theme (system, light, dark), open log and folder
- [x] Dictionary editor for words and fixes, saved to `dictionary.txt`
- [x] The window is its own small program: closing it frees its memory, and settings it saves reach the running app within half a second
- [x] Each Dictionary tab explains what a word or a fix does
- **Checkpoint 8 passed 2026-10-28:** I changed settings and dictionary words from the window, and my next dictations used them

## Phase 9: history
- [x] Save each dictation on this PC (`history.db`), with an on/off switch and Clear history
- [x] History page: search, filter by app, copy
- [x] Home: recent dictations and word counts
- **Checkpoint 9:** a day of dictations shows up in History and on Home

## Phase 10: first run
- [x] A 3 step welcome: speech model download with a progress bar, pick a hotkey, try it
- **Checkpoint 10 passed 2026-10-28:** a first run with an empty model folder downloaded the real model (1.6 GB in about 90 seconds) with live progress, and I walked through the welcome and dictated into it

## Version 1.3.0 released 2026-10-30
Phases 8 to 10: the app window, history, and the first run welcome.

## Phase 11: pill and polish
- [x] Pill on/off (it stays at the bottom center, no position setting)
- [x] Start with Windows
- [x] Mic test meter in Settings
- [x] Six sound styles to pick from (from my sound sheet, added 2026-10-30)
- **Checkpoint 11:** I use each one for a day

## Version 1.4.0 released 2026-10-30
Phase 11: sound styles, pill on/off, Start with Windows, and the mic test.

## Any graphics card (whisper.cpp)
Added 2026-10-31: AMD and Intel cards, and graphics built into the processor, run whisper.cpp through Vulkan. I chose to skip a CPU-only mode.
- [x] Build whisper.cpp with Vulkan ourselves (`scripts/build_whisper_cpp.ps1`); whisper.cpp publishes no Vulkan build for Windows
- [x] Measure it: same words as faster-whisper on every test sentence, 0.06 to 0.24 s on the RTX 4090, about 4 s on the Intel UHD 770 built into the i9
- [x] Compare on my own voice (`scripts/compare_engines.py`, same recordings through every engine): the full-size model differed from faster-whisper by one word in 90 seconds, so NVIDIA cards get the full-size model and other graphics the compressed one
- [x] whisper.cpp engine in Ghostwriter, picking a real graphics card over a built-in chip
- [x] Switch engines in Settings on NVIDIA PCs, live
- [x] Installer: no more NVIDIA-only refusal; non-NVIDIA PCs skip the NVIDIA files and get whisper.cpp
- [ ] I dictate with whisper.cpp on my 4090 for a few days; if it holds up, it becomes the engine for NVIDIA too and the 1.3 GB of NVIDIA files go away
- [ ] A friend's AMD or Intel PC runs the one-line install
- [ ] Build whisper.cpp for Windows the way the Linux build does it, once per processor generation, so PCs without AVX (budget Celerons and Pentiums) don't crash

## Version 1.5.0 released 2026-10-31
Any graphics card: whisper.cpp for AMD, Intel, and built-in graphics, and an engine switch on NVIDIA PCs.

## Phase 12: local AI cleanup (on/off switch, its own page in the app)
- [ ] Small local model on the GPU removes filler words, formats lists, and fixes punctuation
- [ ] Voice commands ("new line", "scratch that")
- [ ] Style by app (raw, casual, or polished per app)
- [ ] Measure the delay against raw mode
- **Checkpoint 12:** I try both and pick my default

## Phase 13: Linux (Omarchy, Hyprland on Wayland)
Added 2026-11-03. Built and tested on my Omarchy laptop (Intel UHD 600, so slow but usable on a small model); a stronger Omarchy laptop comes later. Windows must keep working exactly as it does now.
- [x] Split the Windows-only code from the shared code behind a platform layer (also step one for macOS): `ghostwriter/windows`, picked by `ghostwriter/system.py`
- [x] whisper.cpp built for Linux with Vulkan (`scripts/build_whisper_cpp.sh`). It runs on my laptop, but the UHD 600 is too slow for Whisper: Linux resets the chip mid dictation, so speed waits for a stronger laptop
- [x] Hold-to-talk hotkey by reading the keyboard directly (`/dev/input`, user in the `input` group). I tried Hyprland's global shortcuts first: they reported presses but never releases, and binding Right Alt there locked up my typing. Unlike on Windows, apps still see the key
- [x] Paste: Hyprland presses Ctrl+V (Ctrl+Shift+V in terminals), and `wl-clipboard` saves and restores the clipboard, kept out of clipboard history. I tried `wtype` first, but its keys came out scrambled in older X11 apps like games and once left a key stuck. Only one clipboard format comes back, so formatted text returns as plain text
- [ ] Paste on desktops other than Hyprland (GNOME, KDE), which need another way to press keys
- [x] Knowing which app is in front for History (Hyprland's active window). The name comes from the app's launcher entry, web apps are matched by their address (WhatsApp, YouTube), and Steam games by their window title
- [ ] Tray ghost in Waybar
- [ ] App window through GTK WebKit
- [ ] Listening pill as a Wayland overlay (`gtk-layer-shell`)
- [ ] Start at login (Hyprland autostart) and an app launcher entry (`.desktop` file)
- [ ] One-line install script for Linux (`get.sh`)
- [ ] Check the Windows build still works on my PC before release
- **Checkpoint 13:** I dictate into apps for a day on a Linux laptop strong enough for Whisper

## Later
- macOS (Apple chips only): needs a Mac to test on, and Apple's $99 a year developer program to avoid "unidentified developer" warnings. Shares the window, dictionary, history, sounds, and whisper.cpp (Metal); rebuilds the hotkey (Fn/Globe works on Mac), paste, pill, menu bar icon, start at login, installer, and permission prompts. Step one, doable on Windows: split the Windows-only code from the shared code (done in Phase 13).
- winget (`winget install Vultify.Ghostwriter`), which needs a setup .exe and Microsoft's review
- A real setup wizard (.exe) for people who want a classic installer
- Let Jarvis use Ghostwriter as its ears
