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

Hold **Right Alt**, talk, and let go. The text is pasted where your cursor is, and whatever was on your clipboard is put back right after. Press Ctrl+C in that window to quit.

## Tests

```
.venv\Scripts\python -m pytest tests
```

The tests briefly use the clipboard (and put it back) and pop up a small test window to paste into.

## How it works

- Speech to text: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) running the Whisper large-v3-turbo model on an NVIDIA GPU
- Hold Right Alt to talk (double tap to keep recording hands free is coming next)
- Pastes with the clipboard and Ctrl+V, then restores your clipboard and keeps dictations out of Win+V history
- The mic only opens while you hold the key
- A custom dictionary teaches it names and words it would otherwise miss

## Requirements

- Windows 10 or 11
- An NVIDIA GPU (built and tested on an RTX 4090)
