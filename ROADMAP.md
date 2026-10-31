# Ghostwriter roadmap

Build order I recommend. We check items off as we go.

## Phase 1: foundation
- [x] Python 3.11 kept inside the project (`.python`), venv in `.venv`
- [x] Install faster-whisper with GPU support
- [x] Smoke test: transcribe a short recording on the 4090 and print the time it took (0.16s warm)
- [x] Mic test with Caleb's real voice (`scripts/mic_test.py`): 0.40s, every word right with the word list
- **Checkpoint 1 passed 2026-10-23:** Caleb's voice comes back as correct text in under half a second

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
- **Checkpoint 3 passed 2026-10-24:** Caleb's dictations landed correctly; mic opens in 10 to 18 ms, transcription takes 0.13 to 0.18s

## Phase 4: tray, indicator, and sound
Moved ahead of lock mode, because lock mode keeps recording after you let go and you need to see that.
- [x] Ghost icon in the system tray that turns red while listening, with Quit
- [x] Listening pill at the bottom center of the screen with a live mic level, then "typing" dots; never takes focus and lets clicks through
- [x] Soft sound when listening starts and stops
- **Checkpoint 4 passed 2026-10-24:** tray ghost, listening pill, and sounds all confirmed by Caleb

## Phase 5: lock mode
- [x] Double tap the hotkey to keep recording hands free; tap again to stop (tap under 0.3s, second press within 0.4s, 15 minute safety limit)
- [x] Pill shows a stop square and the start sound plays twice while locked
- **Checkpoint 5 passed 2026-10-24:** Caleb's 66 second ramble came out complete, transcribed in 0.67s

## Phase 6: custom dictionary
Pulled ahead of lock mode on 2026-10-24 so terms that sound different from how they're spelled come out right.
- [x] `dictionary.txt` of words Whisper should know (names, places, and game terms); edits apply without a restart
- [x] Optional find and replace rules for words it still gets wrong (like `my sequel -> MySQL`)
- **Checkpoint 6 passed 2026-10-24:** every dictionary word comes out right in a spoken test run, and a sound-alike game term came out right in Caleb's own voice

## Phase 7: settings and launching
- [x] Settings in the tray menu, saved to `settings.json` (hotkey, mic, sounds), plus Edit dictionary and Open log
- [x] Runs with no console window, logs to `logs/ghostwriter.log`, one copy at a time, error box if it can't start
- [x] Start menu shortcut that launches it with no console window (`scripts/make_shortcut.py`; Caleb runs it himself so it lands in his real Start menu)
- **Checkpoint 7 passed 2026-10-25:** Caleb used it all day on 2026-10-24, including 13 dictations into a game's chat. Felt a little slow to paste while gaming (transcription ~1s with the game on the GPU, vs ~0.2s on the desktop).

## Speed pass (after Checkpoint 7)
- [x] End recording as soon as Caleb goes quiet after letting go (tail ~0.08s, was 0.3s)
- [x] Whisper beam size 5 to 1 (88 ms vs 112 ms per short phrase, same text)
- **Check passed 2026-10-25:** Caleb says it feels faster even on the desktop; transcription 0.09 to 0.15s, no last words clipped

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
Built from Caleb's design (dark and light themes, mint accent, Geist font), shown in a real window through the web engine built into Windows (pywebview).
- [x] Window with its own title bar and a sidebar: Home, Dictionary, Settings, the version, and Check for updates (History joins in Phase 9)
- [x] Closing the window keeps Ghostwriter running in the tray; the tray menu gets Open Ghostwriter (also a left click on the ghost)
- [x] Home: ready card showing the hotkey, a box to try dictating, and quick switches
- [x] Settings: hotkey, hands free on/off and its auto-stop time, mic, sounds, speech model info, theme (system, light, dark), open log and folder
- [x] Dictionary editor for words and fixes, saved to `dictionary.txt`
- [x] The window is its own small program: closing it frees its memory, and settings it saves reach the running app within half a second
- [x] Each Dictionary tab explains what a word or a fix does
- **Checkpoint 8 passed 2026-10-28:** Caleb changed settings and dictionary words from the window, and his next dictations used them

## Phase 9: history
- [x] Save each dictation on this PC (`history.db`), with an on/off switch and Clear history
- [x] History page: search, filter by app, copy
- [x] Home: recent dictations and word counts
- **Checkpoint 9:** a day of dictations shows up in History and on Home

## Phase 10: first run
- [x] A 3 step welcome: speech model download with a progress bar, pick a hotkey, try it
- **Checkpoint 10 passed 2026-10-28:** a first run with an empty model folder downloaded the real model (1.6 GB in about 90 seconds) with live progress, and Caleb walked through the welcome and dictated into it

## Version 1.3.0 released 2026-10-30
Phases 8 to 10: the app window, history, and the first run welcome.

## Phase 11: pill and polish
- [x] Pill on/off (it stays at the bottom center, no position setting)
- [x] Start with Windows
- [x] Mic test meter in Settings
- [x] Six sound styles to pick from (Caleb's sound sheet, added 2026-10-30)
- **Checkpoint 11:** Caleb uses each one for a day

## Phase 12: local AI cleanup (on/off switch, its own page in the app)
- [ ] Small local model on the GPU removes filler words, formats lists, and fixes punctuation
- [ ] Voice commands ("new line", "scratch that")
- [ ] Style by app (raw, casual, or polished per app)
- [ ] Measure the delay against raw mode
- **Checkpoint 12:** Caleb tries both and picks his default

## Later
- winget (`winget install Vultify.Ghostwriter`), which needs a setup .exe and Microsoft's review
- A real setup wizard (.exe) for people who want a classic installer
- Let Jarvis use Ghostwriter as its ears
