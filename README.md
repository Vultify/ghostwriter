# Ghostwriter

I built Ghostwriter because I dictate a lot, and the popular dictation apps cap how many words you can use before you have to pay. Ghostwriter runs speech to text entirely on my own PC, so there are no limits and nothing leaves the machine.

Hold a hotkey, talk, let go, and the text appears wherever the cursor is.

## Status

Version 1.3.0. It's what I use every day instead of Wispr Flow. See [CHANGELOG.md](CHANGELOG.md) for what's in it and [ROADMAP.md](ROADMAP.md) for what's next.

## Install

Open **PowerShell** and paste:

```
irm https://raw.githubusercontent.com/Vultify/ghostwriter/main/get.ps1 | iex
```

That downloads the latest version into a `Ghostwriter` folder in your user folder, installs its own copy of Python and its packages inside that folder, adds Ghostwriter to the Start menu, and starts it. The first start opens a short welcome: it downloads the speech model (about 1.6 GB, one time only) with a progress bar, then lets you pick your hotkey and try it out.

**Updating:** right click the ghost in the tray and choose **Check for updates**, or run the same command again. Your dictionary, settings, and history are kept.

**Without the command:** click **Code**, then **Download ZIP** on GitHub, unzip it wherever you want Ghostwriter to live, and double click **install.bat** in that folder.

Ghostwriter needs an NVIDIA graphics card; the installer checks for one before downloading anything. If an install gets interrupted, running it again picks up where it left off.

## Usage

Open the Start menu, type **Ghostwriter**, and press Enter. The Ghostwriter window opens, and the ghost in the system tray means it's running. Closing the window keeps Ghostwriter running in the tray; click the ghost to open the window again.

To run it in a terminal instead, with the log printed as you go (add `--tray` to start without the window):

```
.venv\Scripts\python -m ghostwriter
```

Only one copy runs at a time; starting it again just opens the window.

Hold the hotkey, talk, and let go. The text is pasted where your cursor is, and whatever was on your clipboard is put back right after. The hotkey is **Right Alt**, or **Right Ctrl** on keyboards where Right Alt is AltGr (it types characters like @ and € there), and you can change it in Settings.

For longer stretches, **double tap the hotkey** to lock recording on and talk hands free. Tap it once more to stop and paste. A quick single tap on its own does nothing, and recording stops by itself after 15 minutes (you can pick 5, 15, or 30) in case it gets left on. Hands free can be turned off in Settings.

- A ghost icon in the system tray shows Ghostwriter is running, and turns red while it listens.
- A small pill at the bottom of the screen shows a live mic level while you talk, then dots while it types. In hands free mode its red dot becomes a stop square.
- A soft sound plays when listening starts and stops. Locking on plays it twice.

## The window

- **Home:** your hotkey, a box to try dictating in, today's word and dictation counts, your latest dictations, and quick switches for sounds, hands free, and the mic
- **History:** everything you've dictated, grouped by day, with search, a filter for each app you use most, and a copy button on each one
- **Dictionary:** add and remove words and fixes
- **Settings:** hotkey, hands free and when it stops, microphone, speech model, light or dark theme (or follow Windows), sounds, saving history on or off, and buttons to open the log, the folder, and `dictionary.txt`
- **Check for updates** at the bottom of the sidebar

The tray menu (right click the ghost) has the hotkey, mic, and sounds too, plus Quit. Changes apply right away and are saved to `settings.json`. The log is at `logs/ghostwriter.log`.

History is saved in `history.db` in the Ghostwriter folder and never leaves your PC. Turn it off in Settings to stop saving new dictations, and **Clear history** on the History page deletes everything saved so far.

The window uses Microsoft WebView2, which comes with Windows 11 and Microsoft Edge.

## Dictionary

`dictionary.txt` is your own list of names and terms for Ghostwriter to spell right. It starts as a copy of `dictionary.example.txt`, which has common app names like GitHub and VS Code, and from there it's yours to edit; updates never touch it. Edit it on the window's Dictionary page, or as a text file with **Edit as text**; changes apply to the next dictation, no restart needed.

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
- The window is its own small program built with [pywebview](https://pywebview.flowrl.com/), so closing it frees its memory and it can never interrupt dictation
- Nothing goes online after the first model download, except when you choose Check for updates

## Requirements

- Windows 10 or 11
- An NVIDIA GPU with CUDA (built and tested on an RTX 4090)
- About 4 GB of disk: 2.4 GB in the Ghostwriter folder plus the 1.6 GB speech model

## License

MIT. See [LICENSE](LICENSE).
