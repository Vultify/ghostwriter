"""Small Linux services the rest of Ghostwriter uses: opening files, message boxes, one copy at a time, the light
or dark theme, and playing sounds."""

import functools
import os
import socket
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from ghostwriter.paths import PROJECT

NAME = "System"  # for labels like "System default"
_PREFER_LIGHT = 2  # the desktop portal's color-scheme: 0 is no preference, 1 prefers dark, 2 prefers light
_held_names: list[socket.socket] = []  # instance locks, held until the process exits


def prepare() -> None:
    """Nothing to set up on Linux."""


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
    samples, rate = _read_wav(path)
    sd.play(samples, rate, blocking=wait)


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
