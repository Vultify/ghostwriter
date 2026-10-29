"""Where Ghostwriter keeps its files. Everything lives inside the folder it was installed to."""

from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = PROJECT / "settings.json"
DICTIONARY_PATH = PROJECT / "dictionary.txt"  # personal, so it isn't in git
STARTER_PATH = PROJECT / "dictionary.example.txt"  # copied to dictionary.txt on first run
HISTORY_PATH = PROJECT / "history.db"  # personal, so it isn't in git
STARTUP_PATH = PROJECT / "startup.json"  # what the tray app is doing as it starts, for the window
LOG_DIR = PROJECT / "logs"
LOG_PATH = LOG_DIR / "ghostwriter.log"
WINDOW_LOG_PATH = LOG_DIR / "window.log"
WEB_DATA_DIR = PROJECT / ".webview"  # the app window's scratch space, cleared on every start
UI_DIR = Path(__file__).resolve().parent / "ui"
ICON_PATH = Path(__file__).resolve().parent / "assets" / "ghostwriter.ico"
