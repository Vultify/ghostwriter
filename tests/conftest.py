"""Shared test helpers: a real text box to paste into, fake key presses, and a guard for the user's clipboard."""

import ctypes
import subprocess
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

import pytest

from ghostwriter import win32
from ghostwriter.clipboard import Clipboard, Snapshot
from ghostwriter.win32 import kernel32, user32

user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, wintypes.LPDWORD]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]


@pytest.fixture(scope="session", autouse=True)
def keep_users_clipboard():
    """Tests overwrite the clipboard, so put back whatever was on it before the run."""
    clipboard = Clipboard()
    saved = clipboard.snapshot()
    yield
    clipboard.restore(saved, user32.GetClipboardSequenceNumber())


@pytest.fixture
def text_box():
    """A small window with a focused text box, brought to the front so Ctrl+V lands in it."""
    root = tk.Tk()
    root.title("Ghostwriter test")
    root.geometry("420x160+80+80")
    root.attributes("-topmost", True)
    box = tk.Text(root)
    box.pack(fill="both", expand=True)
    root.update()
    window = int(root.wm_frame(), 16)
    _bring_to_front(window)
    box.focus_force()
    root.update()
    if user32.GetForegroundWindow() != window:
        root.destroy()
        pytest.skip("Windows would not let the test window come to the front")
    yield root, box
    root.destroy()


def _bring_to_front(window: int) -> None:
    # Windows only lets the app that owns the front window hand over focus, so borrow its input queue.
    front_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    our_thread = kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(our_thread, front_thread, True)
    user32.SetForegroundWindow(window)
    user32.AttachThreadInput(our_thread, front_thread, False)


def pump_until(root: tk.Tk, done, timeout: float = 15.0) -> None:
    """Keep the test window responsive while the code under test runs on another thread."""
    deadline = time.perf_counter() + timeout
    while not done() and time.perf_counter() < deadline:
        root.update()
        time.sleep(0.01)
    root.update()


def run_in_thread(target) -> threading.Thread:
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread


def press_key(vk: int, release: bool = False) -> None:
    event = win32.INPUT(type=win32.INPUT_KEYBOARD)
    event.ki.wVk = vk
    event.ki.dwFlags = win32.KEYEVENTF_KEYUP if release else 0
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(win32.INPUT))


def text_of(snapshot: Snapshot) -> str | None:
    for fmt, data in snapshot:
        if fmt == win32.CF_UNICODETEXT:
            return data.decode("utf-16-le").split("\0", 1)[0]
    return None


def speak_to_wav(text: str, path: Path) -> None:
    """Use the built-in Windows voice to save a sentence as a 16 kHz WAV."""
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, 'Sixteen', 'Mono');"
        f"$s.SetOutputToWaveFile('{path}', $f);"
        f"$s.Speak('{text}');"
        "$s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
