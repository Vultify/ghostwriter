# Ghostwriter

I built Ghostwriter because I dictate a lot, and the popular dictation apps cap how many words you can use before you have to pay. Ghostwriter runs speech to text entirely on my own PC, so there are no limits and nothing leaves the machine.

Hold a hotkey, talk, let go, and the text appears wherever the cursor is.

## Status

Version 1.2.1. It's what I use every day instead of Wispr Flow. See [CHANGELOG.md](CHANGELOG.md) for what's in it and [ROADMAP.md](ROADMAP.md) for what's next.

## Install

Open **PowerShell** and paste:

```
irm https://raw.githubusercontent.com/Vultify/ghostwriter/main/get.ps1 | iex
```

That downloads the latest version into a `Ghostwriter` folder in your user folder, installs its own copy of Python and its packages inside that folder, adds Ghostwriter to the Start menu, and starts it. The first start downloads the speech model (about 1.6 GB, one time only), and a notification tells you when it's ready.

**Updating:** right click the ghost in the tray and choose **Check for updates**, or run the same command again. Your dictionary and settings are kept.

**Without the command:** click **Code**, then **Download ZIP** on GitHub, unzip it wherever you want Ghostwriter to live, and double click **install.bat** in that folder.

Ghostwriter needs an NVIDIA graphics card; the installer checks for one before downloading anything. If an install gets interrupted, running it again picks up where it left off.

## Usage

Open the Start menu, type **Ghostwriter**, and press Enter. It runs in the background with no window; the ghost in the system tray means it's on.

To run it in a terminal instead, with the log printed as you go:

```
.venv\Scripts\python -m ghostwriter
```

Only one copy runs at a time.

Hold the hotkey, talk, and let go. The text is pasted where your cursor is, and whatever was on your clipboard is put back right after. The hotkey is **Right Alt**, or **Right Ctrl** on keyboards where Right Alt is AltGr (it types characters like @ and € there), and you can change it in the tray menu.

For longer stretches, **double tap the hotkey** to lock recording on and talk hands free. Tap it once more to stop and paste. A quick single tap on its own does nothing, and recording stops by itself after 15 minutes in case it gets left on.

- A ghost icon in the system tray shows Ghostwriter is running, and turns red while it listens.
- A small pill at the bottom of the screen shows a live mic level while you talk, then dots while it types. In hands free mode its red dot becomes a stop square.
- A soft sound plays when listening starts and stops. Locking on plays it twice.

## Settings

Right click the ghost in the tray:

- **Hotkey:** Right Alt, Right Ctrl, Caps Lock, Scroll Lock, or Pause
- **Microphone:** the Windows default, or a specific mic (plugged in a new one? restart Ghostwriter to see it)
- **Sounds:** on or off
- **Edit dictionary** and **Open log**
- **Check for updates**
- **Quit Ghostwriter**

Changes apply right away and are saved to `settings.json`. The log is at `logs/ghostwriter.log`.

## Dictionary

`dictionary.txt` is your own list of names and terms for Ghostwriter to spell right. It starts as a copy of `dictionary.example.txt`, which has common app names like GitHub and VS Code, and from there it's yours to edit; updates never touch it. Open it from the tray menu with **Edit dictionary**; changes apply to the next dictation, no restart needed.

```
Your Business Name
Jayson
my sequel -> MySQL
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
- Nothing goes online after the first model download, except when you choose Check for updates

## Requirements

- Windows 10 or 11
- An NVIDIA GPU with CUDA (built and tested on an RTX 4090)
- About 4 GB of disk: 2.4 GB in the Ghostwriter folder plus the 1.6 GB speech model

## License

MIT. See [LICENSE](LICENSE).
