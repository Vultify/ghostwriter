# Ghostwriter roadmap

Build order I recommend. We check items off as we go.

## Phase 1: foundation
- [x] Python 3.11 kept inside the project (`.python`), venv in `.venv`
- [x] Install faster-whisper with GPU support
- [x] Smoke test: transcribe a short recording on the 4090 and print the time it took (0.16s warm)
- [x] Mic test with Caleb's real voice (`scripts/mic_test.py`): 0.40s, every word right with the word list
- **Checkpoint 1 passed 2026-10-23:** Caleb's voice comes back as correct text in under half a second

## Phase 2: design
- [ ] Pasting: clipboard and Ctrl+V, with the old clipboard put back afterward
- [ ] Hotkey: telling a hold from a double tap, and keeping the key away from the app underneath
- [ ] Mic: starting fast enough that the first word is not cut off
- [ ] Knowing which app is in front
- **Checkpoint 2:** lock the approach

## Phase 3: core dictation loop
- [ ] Pick the hotkey (not Ctrl+Win, that is Wispr; not Ctrl+Alt+J, that is Jarvis)
- [ ] Global hotkey: hold to talk
- [ ] Record the mic while the key is held
- [ ] Transcribe with the model kept warm in memory
- [ ] Paste the text where the cursor is
- **Checkpoint 3:** Caleb dictates into Notepad, a browser, and Claude Code, and it lands correctly every time

## Phase 4: lock mode
- [ ] Double tap the hotkey to keep recording hands free; tap again to stop
- **Checkpoint 4:** a long ramble in lock mode comes out complete

## Phase 5: custom dictionary
- [ ] `dictionary.txt` of words Whisper should know (Tulare, Castro Detailing, Supabase)
- [ ] Optional find and replace rules for words it still gets wrong
- **Checkpoint 5:** every dictionary word comes out right in a test run

## Phase 6: tray and indicator
- [ ] Tray icon with quit and settings
- [ ] Small on screen indicator while recording
- [ ] `settings.json` for hotkey, model, and mic
- [ ] Desktop shortcut that launches it with no console window
- **Checkpoint 6:** Caleb uses it for a full day instead of Wispr Flow

## Phase 7: local AI cleanup (on/off switch)
- [ ] Small local model on the GPU cleans filler words and formats lists
- [ ] Measure the delay against raw mode
- **Checkpoint 7:** Caleb tries both and picks his default

## Later
- Start with Windows
- Dictation history
- Voice commands ("new line", "scratch that")
- App aware formatting (casual in Discord, clean in email)
- Let Jarvis use Ghostwriter as its ears
