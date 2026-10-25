# Ghostwriter

I built Ghostwriter because I dictate a lot, and the popular dictation apps cap how many words you can use before you have to pay. Ghostwriter runs speech to text entirely on my own PC, so there are no limits and nothing leaves the machine.

Hold a hotkey, talk, let go, and the text appears wherever the cursor is.

## Status

Version 1.0.0. It's what I use every day instead of Wispr Flow. See [CHANGELOG.md](CHANGELOG.md) for what's in it and [ROADMAP.md](ROADMAP.md) for what's next.

## Setup

You'll need [git](https://git-scm.com/), Python with [uv](https://docs.astral.sh/uv/) (`pip install uv`), and an NVIDIA GPU. In Command Prompt:

```
git clone https://github.com/Vultify/ghostwriter.git
cd ghostwriter
set UV_PYTHON_INSTALL_DIR=%CD%\.python
python -m uv venv .venv --python 3.11 --managed-python
python -m uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.venv\Scripts\python scripts\make_shortcut.py
```

That keeps Python and every package inside the project folder and adds Ghostwriter to the Start menu. The first start downloads the Whisper model (about 1.6 GB).

## Usage

Open the Start menu, type **Ghostwriter**, and press Enter. It runs in the background with no window; the ghost in the system tray means it's on.

To run it in a terminal instead, with the log printed as you go:

```
.venv\Scripts\python -m ghostwriter
```

Only one copy runs at a time.

Hold **Right Alt**, talk, and let go. The text is pasted where your cursor is, and whatever was on your clipboard is put back right after.

For longer stretches, **double tap Right Alt** to lock recording on and talk hands free. Tap it once more to stop and paste. A quick single tap on its own does nothing, and recording stops by itself after 15 minutes in case it gets left on.

- A ghost icon in the system tray shows Ghostwriter is running, and turns red while it listens.
- A small pill at the bottom of the screen shows a live mic level while you talk, then dots while it types. In hands free mode its red dot becomes a stop square.
- A soft sound plays when listening starts and stops. Locking on plays it twice.

## Settings

Right click the ghost in the tray:

- **Hotkey:** Right Alt, Right Ctrl, Caps Lock, Scroll Lock, or Pause
- **Microphone:** the Windows default, or a specific mic (plugged in a new one? restart Ghostwriter to see it)
- **Sounds:** on or off
- **Edit dictionary** and **Open log**
- **Quit Ghostwriter**

Changes apply right away and are saved to `settings.json`. The log is at `logs/ghostwriter.log`.

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

The tests briefly use the clipboard (and put it back) and pop up a small test window to paste into. Leave the PC alone for the 20 or so seconds they take; if another window grabs focus, the paste tests fail on purpose rather than type into it.

## How it works

- Speech to text: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) running the Whisper large-v3-turbo model on an NVIDIA GPU
- A low level keyboard hook catches the hotkey (Right Alt by default) and hides it from the app in front
- Pastes with the clipboard and Ctrl+V, then restores your clipboard and keeps dictations out of Win+V history
- The mic only opens while you're dictating, and recording ends as soon as you go quiet after letting go
- A custom dictionary teaches it names and words it would otherwise miss
- Nothing goes online after the first model download

## Requirements

- Windows 10 or 11
- An NVIDIA GPU with CUDA (built and tested on an RTX 4090)
- About 2 GB of disk for the model

## License

MIT. See [LICENSE](LICENSE).
