"""Pasting on Linux: the clipboard round trip, and real pastes into a test window. Runs on Hyprland."""

import os
import subprocess
import time
import tkinter as tk

import pytest

from conftest import _new_tk, pump_until, run_in_thread
from ghostwriter.linux import hyprland
from ghostwriter.linux.clipboard import SENSITIVE, TEXT, Clipboard, Snapshot
from ghostwriter.linux.paster import Paster, paste_keys

needs_hyprland = pytest.mark.skipif(not hyprland.running(), reason="pasting on Linux needs Hyprland")
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4


class GuardedPaster(Paster):
    """A Paster that refuses to paste unless the test window is in front, so tests never type into the user's apps."""

    def paste(self, text: str) -> bool:
        if hyprland.active_window().get("pid") != os.getpid():
            raise RuntimeError("The test window lost focus, so the paste was skipped")
        return super().paste(text)


@pytest.fixture
def text_box():
    """A small window with a focused text box, waited on until Hyprland says it's in front."""
    root = _new_tk()
    root.title("Ghostwriter test")
    root.geometry("420x160")
    box = tk.Text(root)
    box.pack(fill="both", expand=True)
    box.focus_force()
    pump_until(root, lambda: hyprland.active_window().get("pid") == os.getpid(), timeout=3)
    if hyprland.active_window().get("pid") != os.getpid():
        root.destroy()
        pytest.skip("Hyprland didn't bring the test window to the front")
    yield root, box
    root.destroy()


def copy_from_another_app(text: str) -> None:
    # Marked sensitive like everything the tests copy, so none of it lands in the user's clipboard history.
    subprocess.run(["wl-copy", "--sensitive", text], check=True, start_new_session=True)


@needs_hyprland
def test_pastes_into_the_app_in_front_and_puts_the_clipboard_back(text_box):
    root, box = text_box
    clipboard = Clipboard()
    clipboard.replace(Snapshot(TEXT, "what I copied earlier".encode()))
    result = {}
    worker = run_in_thread(lambda: result.update(restored=GuardedPaster().paste("Hello from Ghostwriter ✓ ")))
    pump_until(root, lambda: not worker.is_alive())
    assert box.get("1.0", "end-1c") == "Hello from Ghostwriter ✓ "
    assert result["restored"] is True
    assert clipboard.snapshot() == Snapshot(TEXT, "what I copied earlier".encode())


@needs_hyprland
def test_dictated_text_is_kept_out_of_clipboard_history():
    clipboard = Clipboard()
    clipboard.write_text("dictated words")
    assert SENSITIVE in clipboard._types()


@needs_hyprland
def test_leaves_the_clipboard_alone_when_something_else_copied_during_the_paste():
    clipboard = Clipboard()
    clipboard.replace(Snapshot(TEXT, b"what I copied earlier"))
    previous = clipboard.snapshot()
    written = clipboard.write_text("dictated words")
    copy_from_another_app("copied in the meantime")
    assert clipboard.restore(previous, written) is False
    assert clipboard.snapshot() == Snapshot(TEXT, b"copied in the meantime")


@needs_hyprland
def test_puts_back_an_image():
    clipboard = Clipboard()
    clipboard.replace(Snapshot("image/png", FAKE_PNG))
    previous = clipboard.snapshot()
    assert previous == Snapshot("image/png", FAKE_PNG)
    assert clipboard.restore(previous, clipboard.write_text("dictated words")) is True
    assert clipboard.snapshot() == Snapshot("image/png", FAKE_PNG)


@needs_hyprland
def test_an_empty_clipboard_stays_empty():
    clipboard = Clipboard()
    clipboard.replace(None)
    assert clipboard.snapshot() is None
    assert clipboard.restore(None, clipboard.write_text("dictated words")) is True
    time.sleep(0.05)  # the replaced wl-copy lets go of the clipboard
    assert clipboard.snapshot() is None


@pytest.mark.parametrize("window, keys", [
    ({"class": "com.mitchellh.ghostty", "tags": ["default-opacity*", "terminal*"]}, ("CTRL SHIFT", "V")),
    ({"class": "org.omarchy.terminal", "tags": ["terminal*"]}, ("CTRL SHIFT", "V")),
    ({"class": "kitty", "tags": []}, ("CTRL SHIFT", "V")),
    ({"class": "chromium", "tags": ["default-opacity*"]}, ("CTRL", "V")),
    ({"class": "steam_app_123", "tags": []}, ("CTRL", "V")),
    ({}, ("CTRL", "V")),
])
def test_terminals_paste_with_ctrl_shift_v_and_everything_else_with_ctrl_v(window, keys):
    assert paste_keys(window) == keys
