# Ghostwriter

I built Ghostwriter because I dictate a lot, and the popular dictation apps cap how many words you can use before you have to pay. Ghostwriter runs speech to text entirely on my own PC, so there are no limits and nothing leaves the machine.

Hold a hotkey, talk, let go, and the text appears wherever the cursor is.

## Status

Early development. See [ROADMAP.md](ROADMAP.md) for what is planned.

## How it works

- Speech to text: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) running the Whisper large-v3-turbo model on an NVIDIA GPU
- Hold the hotkey to talk, or double tap it to keep recording hands free
- A custom dictionary teaches it names and words it would otherwise miss

## Requirements

- Windows 10 or 11
- An NVIDIA GPU (built and tested on an RTX 4090)
