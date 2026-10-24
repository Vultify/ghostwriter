"""The keyboard hook sees Right Alt, reports press and release once each, and hides it from other apps."""

import threading
import time

from conftest import press_key

from ghostwriter import win32
from ghostwriter.hotkey import KeyHook


class Recorded:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.released = threading.Event()

    def press(self) -> None:
        self.events.append("press")

    def release(self) -> None:
        self.events.append("release")
        self.released.set()


def _hook(recorded: Recorded, allow_injected: bool) -> KeyHook:
    hook = KeyHook(win32.VK_RMENU, recorded.press, recorded.release, allow_injected=allow_injected)
    hook.start()
    return hook


def _tap_right_alt_with_repeats() -> None:
    # Holding a key makes Windows repeat the key down message; the hook should report one press.
    for _ in range(3):
        press_key(win32.VK_RMENU)
        time.sleep(0.02)
    press_key(win32.VK_RMENU, release=True)


def test_hook_reports_one_press_and_release_and_swallows_the_key():
    # Hooks run newest first, so the "other app" spy goes in before Ghostwriter's hook.
    spy, ghostwriter = Recorded(), Recorded()
    spy_hook = _hook(spy, allow_injected=True)
    ghostwriter_hook = _hook(ghostwriter, allow_injected=True)
    try:
        _tap_right_alt_with_repeats()
        assert ghostwriter.released.wait(2)
        time.sleep(0.1)
        assert ghostwriter.events == ["press", "release"]
        assert spy.events == []
    finally:
        ghostwriter_hook.stop()
        spy_hook.stop()


def test_hook_ignores_keys_that_software_typed():
    spy, ghostwriter = Recorded(), Recorded()
    spy_hook = _hook(spy, allow_injected=True)
    ghostwriter_hook = _hook(ghostwriter, allow_injected=False)
    try:
        _tap_right_alt_with_repeats()
        assert spy.released.wait(2)
        assert ghostwriter.events == []
    finally:
        ghostwriter_hook.stop()
        spy_hook.stop()
