"""The Ghostwriter app window. It runs as its own small program next to the tray app, so closing it frees all its
memory and a problem in it can never stop dictation. It only reads and writes settings.json, dictionary.txt, and
history.db (plus the Start with Windows shortcut), and reads startup.json to follow the first download; the tray app
notices changes and applies them.

Start it with: python -m ghostwriter.window
"""

import ctypes
import logging
import os
import subprocess
import sys
import winreg
from ctypes import wintypes
from pathlib import Path

from ghostwriter import __version__, shortcuts, sounds, startup, updates, win32
from ghostwriter.audio import loudness
from ghostwriter.dictionary import DictionaryFile
from ghostwriter.history import PAGE_SIZE, History
from ghostwriter.paths import (DICTIONARY_PATH, HISTORY_PATH, ICON_PATH, LOG_PATH, PROJECT, SETTINGS_PATH,
                               STARTUP_PATH, UI_DIR, WEB_DATA_DIR, WINDOW_LOG_PATH)
from ghostwriter.recorder import Recorder, list_microphones
from ghostwriter.settings import HANDS_FREE_MINUTES, HOTKEYS, Settings
from ghostwriter.win32 import dwmapi, kernel32, user32

TITLE = "Ghostwriter"
WIDTH, HEIGHT = 1120, 740
MIN_WIDTH, MIN_HEIGHT = 940, 640
INSTANCE_NAME = "Local\\GhostwriterWindow"
MODEL_LABEL = "Whisper large-v3-turbo"
MODEL_SIZE = "1.6 GB"
BACKGROUNDS = {"dark": "#121316", "light": "#F4F5F6"}  # shown before the page paints, so it never flashes white
NO_WEBVIEW_MESSAGE = (
    "Ghostwriter's window needs Microsoft WebView2, which comes with Windows 11 and Microsoft Edge, and it isn't "
    "on this PC.\n\nGet it from https://go.microsoft.com/fwlink/p/?LinkId=2124703\n\n"
    "Dictation still works: use the ghost in the system tray."
)
_FORM_CLASS = "WindowsForms10."  # the window class pywebview's Windows frames use

log = logging.getLogger("ghostwriter.window")
_instance_mutex = None


class Api:
    """What the page can ask for, through window.pywebview.api. Every call reads the files fresh, because the tray
    menu can change the same settings while the window is open."""

    def __init__(self, settings_path: Path = SETTINGS_PATH, dictionary_path: Path = DICTIONARY_PATH,
                 history_path: Path = HISTORY_PATH, startup_path: Path = STARTUP_PATH,
                 login_folder: Path | None = None) -> None:
        self._settings_path = settings_path
        self._dictionary = DictionaryFile(dictionary_path)
        self._history = History(history_path)
        self._startup_path = startup_path
        self._login_folder = login_folder  # where the Start with Windows shortcut goes; None is Windows' own
        self._mic_test: Recorder | None = None
        # The tray app is downloading the speech model, so this is a new install: open on the welcome.
        self._first_run = startup.read(startup_path).get("model") == "downloading"
        self._window = None
        self._maximized = False
        self._gpu = None

    def attach(self, window) -> None:
        self._window = window

    def state(self) -> dict:
        settings = Settings.load(self._settings_path)
        return {
            "version": __version__,
            "firstRun": self._first_run,
            "settings": {
                "hotkey": settings.hotkey,
                "microphone": settings.microphone,
                "sounds": settings.sounds,
                "hands_free": settings.hands_free,
                "hands_free_minutes": settings.hands_free_minutes,
                "theme": settings.theme,
                "history": settings.history,
                "sound": settings.sound,
                "pill": settings.pill,
            },
            "startWithWindows": shortcuts.starts_with_windows(self._login_folder),
            "soundStyles": list(sounds.STYLES),
            "hotkeys": list(HOTKEYS),
            "microphones": list_microphones(),
            "handsFreeMinutes": list(HANDS_FREE_MINUTES),
            "model": MODEL_LABEL,
            "modelSize": MODEL_SIZE,
            "gpu": self._gpu_name(),
        }

    def set_setting(self, name: str, value) -> dict:
        Settings.load(self._settings_path).change(name, value)
        return self.state()

    def dictionary(self) -> dict:
        return self._dictionary.entries()

    def add_word(self, word: str) -> dict:
        return self._edit(self._dictionary.add_word, word)

    def remove_word(self, word: str) -> dict:
        return self._edit(self._dictionary.remove_word, word)

    def add_fix(self, heard: str, write: str) -> dict:
        return self._edit(self._dictionary.add_fix, heard, write)

    def remove_fix(self, heard: str, write: str) -> dict:
        return self._edit(self._dictionary.remove_fix, heard, write)

    def set_start_with_windows(self, on: bool) -> dict:
        shortcuts.set_start_with_windows(bool(on), self._login_folder)
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
        return {**self._history.search(query, app or None, limit), "apps": self._history.apps()}

    def history_summary(self) -> dict:
        return self._history.summary()

    def history_stamp(self) -> str:
        return self._history.stamp()

    def clear_history(self) -> None:
        self._history.clear()

    def open_log(self) -> None:
        os.startfile(LOG_PATH if LOG_PATH.exists() else LOG_PATH.parent)

    def open_folder(self) -> None:
        os.startfile(PROJECT)

    def open_dictionary_file(self) -> None:
        self._dictionary.current()  # makes sure the file exists first
        os.startfile(self._dictionary.path)

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
        updates.start_update()  # get.ps1 closes this window too while it updates

    def minimize(self) -> None:
        self._window.minimize()

    def toggle_maximize(self) -> None:
        if self._maximized:
            self._window.restore()
        else:
            self._window.maximize()
        self._maximized = not self._maximized

    def close(self) -> None:
        self.stop_mic_test()
        self._window.destroy()

    def _edit(self, change, *values) -> dict:
        try:
            change(*values)
        except ValueError as error:
            return {**self._dictionary.entries(), "error": str(error)}
        return self._dictionary.entries()

    def _gpu_name(self) -> str:
        if self._gpu is None:
            try:
                result = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                        capture_output=True, text=True, timeout=5,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                self._gpu = result.stdout.strip().splitlines()[0] if result.returncode == 0 else "NVIDIA GPU"
            except (OSError, IndexError, subprocess.SubprocessError):
                self._gpu = "NVIDIA GPU"
        return self._gpu


def open_window() -> None:
    """Start the app window, or bring it to the front if it's already open. Called from the tray app."""
    user32.AllowSetForegroundWindow(win32.ASFW_ANY)
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(pythonw if pythonw.exists() else sys.executable), "-m", "ghostwriter.window"], cwd=PROJECT)


def close_window() -> None:
    """Close the app window, if it's open. Called when Ghostwriter quits."""
    for window in _app_windows():
        user32.PostMessageW(window, win32.WM_CLOSE, 0, 0)


def windows_theme() -> str:
    """Whether Windows is set to light or dark mode for apps."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 1 else "dark"
    except OSError:
        return "dark"


def _app_windows() -> list[int]:
    """The app window's handle, found by its title and frame type and by running from this install folder."""
    found = []

    def check(window, _):
        title = ctypes.create_unicode_buffer(64)
        frame = ctypes.create_unicode_buffer(128)
        user32.GetWindowTextW(window, title, len(title))
        user32.GetClassNameW(window, frame, len(frame))
        if title.value == TITLE and frame.value.startswith(_FORM_CLASS) and _runs_from_here(window):
            found.append(window)
        return True

    user32.EnumWindows(win32.WNDENUMPROC(check), 0)
    return found


def _runs_from_here(window: int) -> bool:
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
    if process_id.value == os.getpid():
        return False
    process = kernel32.OpenProcess(win32.PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
    if not process:
        return False
    try:
        name = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(name))
        if not kernel32.QueryFullProcessImageNameW(process, 0, name, ctypes.byref(size)):
            return False
        return name.value.lower().startswith(str(PROJECT).lower())
    finally:
        kernel32.CloseHandle(process)


def _bring_to_front() -> None:
    for window in _app_windows():
        user32.ShowWindow(window, win32.SW_RESTORE)
        user32.SetForegroundWindow(window)


def _claim_window_slot() -> bool:
    """Only one app window at a time; returns False if one is already open."""
    global _instance_mutex
    ctypes.set_last_error(0)
    _instance_mutex = kernel32.CreateMutexW(None, False, INSTANCE_NAME)  # held until this program exits
    return ctypes.get_last_error() != win32.ERROR_ALREADY_EXISTS


def _style_frame(window) -> None:
    """Round the corners on Windows 11, set the real size, and keep a maximized window off the taskbar."""
    from System import Action  # available once pywebview has loaded .NET
    from System.Drawing import Point, Size
    from System.Windows.Forms import Screen

    form = window.native
    corner = ctypes.c_int(win32.DWMWCP_ROUND)
    dwmapi.DwmSetWindowAttribute(form.Handle.ToInt64(), win32.DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner),
                                 ctypes.sizeof(corner))

    def resize() -> None:
        # Dropping the border shrinks the window by the border's size, so set the size again afterwards.
        area = Screen.FromHandle(form.Handle).WorkingArea
        scale = form.DeviceDpi / 96
        width, height = round(WIDTH * scale), round(HEIGHT * scale)
        form.Size = Size(width, height)
        form.Location = Point(area.X + (area.Width - width) // 2, area.Y + (area.Height - height) // 2)
        form.MaximizedBounds = area

    form.Invoke(Action(resize))  # window changes have to happen on the window's own thread


def main() -> None:
    WINDOW_LOG_PATH.parent.mkdir(exist_ok=True)
    logging.basicConfig(filename=WINDOW_LOG_PATH, level=logging.WARNING, encoding="utf-8",
                        format="%(asctime)s  %(name)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    if not _claim_window_slot():
        _bring_to_front()
        return

    import webview  # loaded here so the tray app can import this module without loading a browser

    api = Api()
    theme = Settings.load().theme
    window = webview.create_window(
        TITLE,
        url=str(UI_DIR / "index.html"),
        js_api=api,
        width=WIDTH,
        height=HEIGHT,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        frameless=True,
        easy_drag=False,
        background_color=BACKGROUNDS[windows_theme() if theme == "system" else theme],
    )
    api.attach(window)
    window.events.shown += lambda: _style_frame(window)
    try:
        webview.start(gui="edgechromium", http_server=True, private_mode=True, storage_path=str(WEB_DATA_DIR),
                      icon=str(ICON_PATH))
    except Exception:
        log.exception("The app window couldn't start")
        user32.MessageBoxW(None, NO_WEBVIEW_MESSAGE, TITLE, win32.MB_ICONERROR)


if __name__ == "__main__":
    main()
