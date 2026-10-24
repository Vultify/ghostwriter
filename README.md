# Ghostwriter

I built Ghostwriter because I dictate a lot, and the popular dictation apps cap how many words you can use before you have to pay. Ghostwriter runs speech to text entirely on my own PC, so there are no limits and nothing leaves the machine.

Hold a hotkey, talk, let go, and the text appears wherever the cursor is.

## Status

Early development. Hold to talk works; see [ROADMAP.md](ROADMAP.md) for what's next.

## Usage

From the project folder:

```
.venv\Scripts\python -m ghostwriter
```

Hold **Right Alt**, talk, and let go. The text is pasted where your cursor is, and whatever was on your clipboard is put back right after.

For longer stretches, **double tap Right Alt** to lock recording on and talk hands free. Tap it once more to stop and paste. A quick single tap on its own does nothing, and recording stops by itself after 15 minutes in case it gets left on.

- A ghost icon in the system tray shows Ghostwriter is running, and turns red while it listens.
- A small pill at the bottom of the screen shows a live mic level while you talk, then dots while it types. In hands free mode its red dot becomes a stop square.
- A soft sound plays when listening starts and stops. Locking on plays it twice.

Quit from the tray icon (right click, Quit Ghostwriter) or press Ctrl+C in the terminal.

## Dictionary

`dictionary.txt` teaches Ghostwriter names and terms. Changes apply to the next dictation, no restart needed.

```
Castro Detailing
Wardogs
sea whiz, sea whizzes -> CIWS
```

A plain line is a word to spell right. A line with `->` is a fix: what Whisper hears on the left (several versions split by commas), what you want on the right. Fixes ignore capital letters and work with or without spaces or hyphens.

## Tests

```
.venv\Scripts\python -m pytest tests
```

The tests briefly use the clipboard (and put it back) and pop up a small test window to paste into.

## How it works

- Speech to text: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) running the Whisper large-v3-turbo model on an NVIDIA GPU
- Hold Right Alt to talk, or double tap it to keep recording hands free
- Pastes with the clipboard and Ctrl+V, then restores your clipboard and keeps dictations out of Win+V history
- The mic only opens while you hold the key
- A custom dictionary teaches it names and words it would otherwise miss

## Requirements

- Windows 10 or 11
- An NVIDIA GPU (built and tested on an RTX 4090)
