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
- **Checkpoint 4 passed 2026-10-24:** tray ghost, listening pill, and sounds all confirmed by Caleb; "Wardogs" now spelled right

## Phase 5: lock mode
- [x] Double tap the hotkey to keep recording hands free; tap again to stop (tap under 0.3s, second press within 0.4s, 15 minute safety limit)
- [x] Pill shows a stop square and the start sound plays twice while locked
- **Checkpoint 5 passed 2026-10-24:** Caleb's 66 second ramble came out complete, transcribed in 0.67s

## Phase 6: custom dictionary
Pulled ahead of lock mode on 2026-10-24 so Wardogs terms like CIWS ("sea whiz") come out right.
- [x] `dictionary.txt` of words Whisper should know (Tulare, Castro Detailing, Supabase, Wardogs, CIWS); edits apply without a restart
- [x] Optional find and replace rules for words it still gets wrong (`sea whiz -> CIWS`)
- **Checkpoint 6 passed 2026-10-24:** every dictionary word comes out right in a spoken test run, and Caleb's "CIWS" came out right in his own voice

## Phase 7: settings and launching
- [ ] Settings in the tray menu, saved to `settings.json` (hotkey, mic, sounds)
- [ ] Desktop shortcut that launches it with no console window
- **Checkpoint 7:** Caleb uses it for a full day instead of Wispr Flow

## Phase 8: local AI cleanup (on/off switch)
- [ ] Small local model on the GPU cleans filler words and formats lists
- [ ] Measure the delay against raw mode
- **Checkpoint 8:** Caleb tries both and picks his default

## Later
- Installer so other people can use Ghostwriter
- Start with Windows
- Dictation history
- Voice commands ("new line", "scratch that")
- App aware formatting (casual in Discord, clean in email)
- Let Jarvis use Ghostwriter as its ears
