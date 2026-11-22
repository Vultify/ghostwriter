"""The Ghostwriter app window. It runs as its own small program next to the tray app, so closing it frees all its
memory and a problem in it can never stop dictation. It only reads and writes settings.json, dictionary.txt, and
history.db (plus the start at login shortcut), and reads startup.json to follow the first download; the tray app
notices changes and applies them.

Start it with: python -m ghostwriter.window
"""

import hashlib
import logging
import subprocess
from pathlib import Path

from ghostwriter import __version__, app_icons, models, sounds, startup, updates
from ghostwriter.audio import loudness
from ghostwriter.dictionary import AddedDates, DictionaryFile, entry_key, fix_line
from ghostwriter.history import FILTER_APPS, MENU_APPS, PAGE_SIZE, History
from ghostwriter.paths import (APP_ICONS_DIR, DICTIONARY_DATES_PATH, DICTIONARY_PATH, HISTORY_PATH, ICON_PATH,
                               LOG_PATH, OWN_APP, PROJECT, SETTINGS_PATH, STARTUP_PATH, UI_DIR, WEB_DATA_DIR, WINDOW_LOG_PATH)
from ghostwriter.recorder import Recorder, list_microphones
from ghostwriter.settings import HANDS_FREE_MINUTES, HOTKEYS, OTHER_SOUNDS, Settings
from ghostwriter.system import app_window, desktop, hotkey, processes, shortcuts
from ghostwriter.whisper_cpp import PROCESSOR

TITLE = "Ghostwriter"
WIDTH, HEIGHT = 1360, 920  # roomy enough that every page fits without wrapping, on screens big enough for it
MIN_WIDTH, MIN_HEIGHT = 940, 640
INSTANCE_NAME = "GhostwriterWindow"
MODEL_LABEL = "Whisper large-v3-turbo"
BACKGROUNDS = {"dark": "#0C1014", "light": "#F4F5F6"}  # shown before the page paints, so it never flashes white

log = logging.getLogger("ghostwriter.window")


class Api:
    """What the page can ask for, through window.pywebview.api. Every call reads the files fresh, because the tray
    menu can change the same settings while the window is open."""

    def __init__(self, settings_path: Path = SETTINGS_PATH, dictionary_path: Path = DICTIONARY_PATH,
                 history_path: Path = HISTORY_PATH, startup_path: Path = STARTUP_PATH,
                 login_folder: Path | None = None, icons_folder: Path = APP_ICONS_DIR,
                 dates_path: Path = DICTIONARY_DATES_PATH) -> None:
        self._settings_path = settings_path
        self._icons_folder = icons_folder
        self._dictionary = DictionaryFile(dictionary_path)
        self._dates = AddedDates(dates_path)
        self._history = History(history_path)
        self._startup_path = startup_path
        self._login_folder = login_folder  # where the start at login shortcut goes; None is the system's own
        self._mic_test: Recorder | None = None
        # The tray app is downloading the speech model for a new install, so open on the welcome.
        status = startup.read(startup_path)
        self._first_run = status.get("model") == "downloading" and status.get("first_run", False)
        self._window = None
        self._maximized = False
        self._last_settings: Settings | None = None
        self._nvidia: str | None = None
        self._nvidia_checked = False
        self._tray_has_nvidia: bool | None = None  # the tray app's last answer, kept through torn reads

    def attach(self, window) -> None:
        self._window = window
        # Follow the real window state, which also changes from the tray, Windows snapping, or a double click.
        window.events.maximized += lambda: setattr(self, "_maximized", True)
        window.events.restored += lambda: setattr(self, "_maximized", False)

    def state(self) -> dict:
        settings = Settings.load(self._settings_path)
        if settings.readable:
            self._last_settings = settings
        elif self._last_settings:  # unreadable for now: show what was last read, not the defaults
            settings = self._last_settings
        status = startup.read(self._startup_path)
        has_nvidia = self._has_nvidia(status)
        engine = models.resolve(settings.engine, has_nvidia)
        return {
            "version": __version__,
            "firstRun": self._first_run,
            "settings": settings.saved(),
            "system": desktop.NAME,
            "ownFrame": app_window.OWN_FRAME,
            "ownApp": OWN_APP,
            "appMenu": desktop.APP_MENU,
            "startAtLogin": shortcuts.starts_at_login(self._login_folder),
            "soundStyles": list(sounds.STYLES),
            "hotkeys": list(HOTKEYS),
            "hotkeyHidden": hotkey.HIDES_KEY,
            "desktopKeys": hotkey.desktop_keys(),
            "microphones": list_microphones(),
            "handsFreeMinutes": list(HANDS_FREE_MINUTES),
            "otherSounds": list(OTHER_SOUNDS),
            "pageSize": PAGE_SIZE,
            "filterApps": FILTER_APPS,
            "engine": engine,
            "engines": models.available(has_nvidia),
            "model": f"{MODEL_LABEL}, compressed" if models.compressed(engine, has_nvidia) else MODEL_LABEL,
            "modelSize": models.size(engine, has_nvidia),
            "modelDownloaded": models.downloaded(engine, has_nvidia),
            "gpu": self._runs_on(engine, status),
            "status": status,
        }

    def set_setting(self, name: str, value) -> dict:
        if Settings.load(self._settings_path).change(name, value):
            return self.state()
        return {**self.state(), "settingsError": "settings.json can't be read right now, so that change wasn't saved. "
                                                 "Try again in a few seconds."}

    def dictionary(self) -> dict:
        """The words and fixes, each with the day it was added, or an error when the file can't be read."""
        try:
            entries = self._dictionary.entries()
        except ValueError as error:
            return {"words": [], "fixes": [], "error": str(error)}
        lines = [*entries["words"], *(fix_line(fix["heard"], fix["write"]) for fix in entries["fixes"])]
        added = self._dates.dates(lines)
        return {
            "words": [{"text": word, "added": added[entry_key(word)]} for word in entries["words"]],
            "fixes": [{**fix, "added": added[entry_key(fix_line(fix["heard"], fix["write"]))]} for fix in entries["fixes"]],
        }

    def add_word(self, word: str) -> dict:
        return self._edit(self._dictionary.add_word, word)

    def remove_word(self, word: str) -> dict:
        return self._edit(self._dictionary.remove_word, word)

    def add_fix(self, heard: str, write: str) -> dict:
        return self._edit(self._dictionary.add_fix, heard, write)

    def remove_fix(self, heard: str, write: str) -> dict:
        return self._edit(self._dictionary.remove_fix, heard, write)

    def change_word(self, old: str, new: str) -> dict:
        return self._edit(lambda: self._dates.moved(old, self._dictionary.change_word(old, new)))

    def change_fix(self, old_heard: str, old_write: str, heard: str, write: str) -> dict:
        return self._edit(lambda: self._dates.moved(fix_line(old_heard, old_write),
                                                    self._dictionary.change_fix(old_heard, old_write, heard, write)))

    def import_dictionary(self) -> dict:
        """Add the words and fixes from a text file the person picks."""
        import webview

        picked = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=("Text files (*.txt)", "All files (*)"))
        if not picked:
            return self.dictionary()
        try:
            text = Path(picked[0]).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            return {**self.dictionary(), "message": "Couldn't read that file. Pick a plain text file."}
        words, fixes = self._dictionary.merge(text)
        found = " and ".join(part for part in (_count(words, "word"), _count(fixes, "fix", "fixes")) if part)
        return {**self.dictionary(), "message": f"Added {found}." if found else "Nothing new in that file."}

    def export_dictionary(self) -> dict:
        """Save a copy of dictionary.txt where the person picks."""
        import webview

        self._dictionary.current()  # makes sure the file exists first
        picked = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename="dictionary.txt",
                                                 file_types=("Text files (*.txt)",))
        target = picked if isinstance(picked, str) else (picked[0] if picked else None)
        if not target:
            return {"message": ""}
        try:
            Path(target).write_text(self._dictionary.text(), encoding="utf-8")
        except ValueError as error:
            return {"message": str(error)}
        except OSError:
            return {"message": "Couldn't save there. Try another folder."}
        return {"message": f"Saved a copy as {Path(target).name}."}

    def set_start_at_login(self, on: bool) -> dict:
        shortcuts.set_start_at_login(bool(on), self._login_folder)
        return self.state()

    def preview_sound(self, style: str) -> None:
        if style in sounds.STYLES:
            sounds.preview(style)

    def start_mic_test(self) -> bool:
        """Open the chosen mic so the page can show its level. Returns whether it opened."""
        self.stop_mic_test()
        test = Recorder(microphone=Settings.load(self._settings_path).microphone)
        try:
            test.start()
        except Exception as error:
            log.warning("Couldn't open the mic for a test: %s", error)
            return False
        self._mic_test = test
        return True

    def mic_level(self) -> float:
        test = self._mic_test
        return loudness(test.level) if test else 0.0

    def stop_mic_test(self) -> None:
        test, self._mic_test = self._mic_test, None
        if test:
            test.stop()

    def startup_status(self) -> dict:
        return startup.read(self._startup_path)

    def history(self, query: str = "", app: str = "", limit: int = PAGE_SIZE) -> dict:
        return {**self._history.search(query, app or None, limit), "apps": self._history.apps(FILTER_APPS + MENU_APPS)}

    def history_summary(self) -> dict:
        return self._history.summary()

    def app_icons(self, names: list[str]) -> dict[str, str]:
        return app_icons.data_urls(list(names)[:100], self._icons_folder)

    def history_stamp(self) -> str:
        return self._history.stamp()

    def settings_stamp(self) -> str:
        """Changes whenever settings.json is saved, by the window or the tray menu, and when a desktop's own dictation
        keys take over or let go."""
        # From the file's contents, since two saves in the same Windows clock tick share a modified time.
        try:
            saved = hashlib.sha256(self._settings_path.read_bytes()).hexdigest()[:16]
        except OSError:
            saved = ""
        return f"{saved} {hotkey.desktop_keys()}"

    def delete_dictation(self, dictation_id: int) -> None:
        self._history.delete(dictation_id)

    def clear_history(self) -> None:
        self._history.clear()

    def open_log(self) -> None:
        desktop.open_path(LOG_PATH if LOG_PATH.exists() else LOG_PATH.parent)

    def open_folder(self) -> None:
        desktop.open_path(PROJECT)

    def open_dictionary_file(self) -> None:
        self._dictionary.current()  # makes sure the file exists first
        desktop.open_path(self._dictionary.path)

    def check_for_updates(self) -> dict:
        if updates.is_git_checkout():
            return {"status": "git"}
        try:
            latest = updates.latest_version()
        except Exception as error:
            log.warning("Couldn't check for updates: %s", error)
            return {"status": "error"}
        return {"status": "available" if updates.is_newer(latest) else "current", "latest": latest}

    def start_update(self) -> None:
        updates.start_update()  # the installer closes this window too while it updates

    def minimize(self) -> None:
        self._window.minimize()

    def toggle_maximize(self) -> None:
        if self._maximized:  # also kept up to date by the window's maximized and restored events
            self._window.restore()
            self._maximized = False
        else:
            self._window.maximize()
            self._maximized = True

    def close(self) -> None:
        self.stop_mic_test()
        self._window.destroy()

    def _edit(self, change, *values) -> dict:
        try:
            change(*values)
        except ValueError as error:
            return {**self.dictionary(), "error": str(error)}
        return self.dictionary()

    def _has_nvidia(self, status: dict) -> bool:
        """Whether the tray app runs faster-whisper on an NVIDIA card. Its own answer is in startup.json; before
        it has written one, a card nvidia-smi can see is the best guess."""
        has_nvidia = status.get("has_nvidia")
        if isinstance(has_nvidia, bool):
            self._tray_has_nvidia = has_nvidia
        if self._tray_has_nvidia is not None:
            return self._tray_has_nvidia
        return self._nvidia_name() is not None

    def _nvidia_name(self) -> str | None:
        """The NVIDIA card's name, or None on a PC without one."""
        if not self._nvidia_checked:
            self._nvidia_checked = True
            try:
                result = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                        capture_output=True, text=True, timeout=5,
                                        creationflags=processes.NO_WINDOW)
                if result.returncode == 0 and result.stdout.strip():
                    self._nvidia = result.stdout.strip().splitlines()[0]
            except (OSError, subprocess.SubprocessError):
                pass
        return self._nvidia

    def _runs_on(self, engine: str, status: dict) -> str:
        if engine == models.FASTER_WHISPER:
            return self._nvidia_name() or "Your graphics card"
        # whisper.cpp says which graphics it picked once it's running.
        device = status.get("device") if status.get("engine") == engine else None
        if device == PROCESSOR:
            return "Your processor (slow)"
        return device or "Your graphics card"


def _count(number: int, one: str, many: str | None = None) -> str:
    return "" if not number else f"1 {one}" if number == 1 else f"{number} {many or one + 's'}"


def _fitted_size(screens: list) -> tuple[int, int]:
    """The window's size, shrunk to leave room around it on a small screen, but never below the page's minimum."""
    if not screens:
        return WIDTH, HEIGHT
    screen = screens[0]
    return (max(MIN_WIDTH, min(WIDTH, int(screen.width * 0.9))),
            max(MIN_HEIGHT, min(HEIGHT, int(screen.height * 0.85))))


def open_window() -> None:
    """Start the app window, or bring it to the front if it's already open. Called from the tray app."""
    app_window.open_window()


def close_window() -> None:
    """Close the app window, if it's open. Called when Ghostwriter quits."""
    app_window.close_window(TITLE)


def main() -> None:
    WINDOW_LOG_PATH.parent.mkdir(exist_ok=True)
    logging.basicConfig(filename=WINDOW_LOG_PATH, level=logging.WARNING, encoding="utf-8",
                        format="%(asctime)s  %(name)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    if not desktop.claim_single_instance(INSTANCE_NAME):
        app_window.bring_to_front(TITLE)
        return

    import webview  # loaded here so the tray app can import this module without loading a browser

    api = Api()
    theme = Settings.load().theme
    width, height = _fitted_size(webview.screens)
    window = webview.create_window(
        TITLE,
        url=str(UI_DIR / "index.html"),
        js_api=api,
        width=width,
        height=height,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        frameless=app_window.OWN_FRAME,
        easy_drag=False,
        background_color=BACKGROUNDS[desktop.apps_theme() if theme == "system" else theme],
    )
    api.attach(window)
    window.events.shown += lambda: app_window.style_frame(window, width, height)
    try:
        webview.start(gui=app_window.WEB_ENGINE, http_server=True, private_mode=True, storage_path=str(WEB_DATA_DIR),
                      icon=str(ICON_PATH))
    except Exception:
        log.exception("The app window couldn't start")
        desktop.show_error(app_window.MISSING_ENGINE_MESSAGE)


if __name__ == "__main__":
    main()
