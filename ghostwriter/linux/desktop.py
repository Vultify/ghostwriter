"""Small Linux services the rest of Ghostwriter uses: opening files, message boxes, one copy at a time, the light
or dark theme, and playing sounds."""

import functools
import os
import signal
import socket
import subprocess
import sys
import threading
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from ghostwriter.linux import hotkey
from ghostwriter.paths import PROJECT

# For labels like "Omarchy default" and "Start with Omarchy": the desktop's name where it has its own, else Linux.
NAME = "Omarchy" if Path("/usr/share/omarchy").is_dir() else "Linux"
APP_MENU = "app launcher"  # where people find Ghostwriter to start it again
_PREFER_LIGHT = 2  # the desktop portal's color-scheme: 0 is no preference, 1 prefers dark, 2 prefers light
_held_names: list[socket.socket] = []  # instance locks, held until the process exits
_player_lock = threading.Lock()
_playing: "_Playback | None" = None  # the last sound started


def prepare() -> None:
    """Quit cleanly on Ctrl+C and on a plain terminate (logging out, or Quit in Omarchy's panel), however Ghostwriter
    was started: launchers often start programs with Ctrl+C ignored, and Python keeps it ignored. Called once, from
    the main thread, when the tray app starts. Omarchy's dictation keys are caught from here on too."""
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    hotkey.catch_signals()


def claim_single_instance(name: str) -> bool:
    """Return False if another program already claimed this name, like a second copy of Ghostwriter. The name is an
    abstract socket, which Linux frees the moment its process ends, even after a crash."""
    lock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        lock.bind(f"\0{name}-{os.getuid()}")  # the user id keeps two people on one PC apart
    except OSError:
        lock.close()
        return False
    _held_names.append(lock)
    return True


def open_path(path: Path) -> None:
    """Open a file or folder in the app the desktop uses for it."""
    subprocess.Popen(["xdg-open", str(path)], start_new_session=True, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def show_error(text: str) -> None:
    _dialog("error", text)


def ask_yes_no(question: str) -> bool:
    return _dialog("question", question)


def apps_theme() -> str:
    """Whether the desktop is set to light or dark mode for apps."""
    return "light" if _color_scheme() == _PREFER_LIGHT else "dark"


def taskbar_is_light() -> bool:
    """Linux bars follow the desktop's theme, so a light theme means a light bar."""
    return _color_scheme() == _PREFER_LIGHT


def play_sound(path: Path, wait: bool = False) -> None:
    """Play a WAV file. Returns right away unless wait is set, and a new sound cuts off one still playing. It plays
    from Ghostwriter itself, so turning other apps down while listening never turns down its own sounds."""
    global _playing
    samples, rate = _read_wav(path)
    # One sound at a time, started and stopped by one thread at a time: the sound library crashes the whole program
    # when two threads stop and start sounds together, like quick clicks through the sound previews.
    with _player_lock:
        if _playing is not None:
            _playing.stop()
        _playing = playback = _Playback(samples, rate)
    if wait:
        playback.finished.wait()


class _Playback:
    """One sound playing on the default speaker."""

    def __init__(self, samples: np.ndarray, rate: int) -> None:
        self.samples = samples
        self.position = 0
        self.finished = threading.Event()
        self.closed = False
        self.stream = sd.OutputStream(samplerate=rate, channels=samples.shape[1], dtype="int16",
                                      callback=self._fill, finished_callback=self.finished.set)
        try:
            self.stream.start()
        except Exception:
            self.stream.close()
            raise
        threading.Thread(target=self._close_when_done, daemon=True).start()

    def stop(self) -> None:
        """Cut the sound off and let go of the speaker. Called with the player lock held."""
        if not self.closed:
            self.closed = True
            self.stream.abort()
            self.stream.close()
        self.finished.set()

    def _close_when_done(self) -> None:
        # A sound that plays to its end still holds the speaker until it's closed, and the sound library doesn't
        # allow closing it from its own callback.
        self.finished.wait()
        with _player_lock:
            self.stop()

    def _fill(self, out: np.ndarray, frames: int, time, status) -> None:
        chunk = self.samples[self.position:self.position + frames]
        out[:len(chunk)] = chunk
        out[len(chunk):] = 0
        self.position += frames
        if len(chunk) < frames:
            raise sd.CallbackStop


@functools.cache
def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as sound:
        samples = np.frombuffer(sound.readframes(sound.getnframes()), dtype=np.int16)
        return samples.reshape(-1, sound.getnchannels()), sound.getframerate()


def _dialog(kind: str, text: str) -> bool:
    """Show a message box as a small program of its own, so it works from any thread, before the tray is up or
    after something broke. True when the answer is yes."""
    return subprocess.run([sys.executable, "-m", "ghostwriter.linux.dialog", kind, text], cwd=PROJECT).returncode == 0


def _color_scheme() -> int | None:
    """The desktop's light or dark preference, from the desktop portal that GNOME, KDE, and Hyprland all run."""
    from gi.repository import Gio, GLib

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                              "org.freedesktop.portal.Settings", "ReadOne",
                              GLib.Variant("(ss)", ("org.freedesktop.appearance", "color-scheme")),
                              GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, 1000, None)
        return reply.unpack()[0]
    except GLib.Error:  # no portal running, or one too old to answer
        return None
