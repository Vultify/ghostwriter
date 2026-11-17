"""The listening pill on Linux: an overlay layer at the bottom center of the screen in use, which never takes the
keyboard and goes away when it's hidden or Ghostwriter closes."""

import json
import os
import sys
import time

import pytest

if sys.platform != "linux":  # skipped here rather than in conftest, so a Linux-only change stays out of shared files
    pytest.skip("Linux only", allow_module_level=True)

from ghostwriter import indicator  # noqa: E402
from ghostwriter.indicator import Indicator  # noqa: E402
from ghostwriter.linux import hyprland, pill, pill_overlay  # noqa: E402
from ghostwriter.state import State  # noqa: E402

needs_hyprland = pytest.mark.skipif(not hyprland.running(), reason="needs Hyprland's overlay layers")


def _pill_layers() -> list[tuple[str, dict]]:
    found = []
    for monitor, details in json.loads(hyprland.request("j/layers")).items():
        for level, layers in details["levels"].items():
            found += [(monitor, {**layer, "level": level}) for layer in layers
                      if layer["namespace"] == pill_overlay.NAMESPACE]
    return found


def _wait_for(condition, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def _window():
    return pill.PillWindow(indicator.WIDTH, indicator.HEIGHT, indicator.BOTTOM_MARGIN)


def _show(window):
    """Send one frame, the way the indicator does: take up the scale, draw, present."""
    window.pump()
    frame = indicator._draw(State.LISTENING, [0.5] * indicator.BAR_COUNT, 0, window.size, window.scale)
    window.present(frame, 1.0)


@needs_hyprland
def test_the_pill_shows_at_the_bottom_center_of_the_screen_in_use_without_taking_the_keyboard():
    focused = next(monitor for monitor in json.loads(hyprland.request("j/monitors")) if monitor["focused"])
    in_front = hyprland.active_window().get("address")
    shown = Indicator(level=lambda: 0.05)
    shown.start()
    try:
        shown.show(State.LISTENING)
        # Hyprland lists a new layer at a stand-in size until its first frame arrives.
        assert _wait_for(lambda: [(layer["w"], layer["h"]) for _, layer in _pill_layers()]
                         == [(indicator.WIDTH, indicator.HEIGHT)])
        [(monitor, layer)] = _pill_layers()
        assert monitor == focused["name"] and layer["level"] == "3"  # overlay, above windows and bars
        reserved_bottom = focused["reserved"][3]
        scale = focused["scale"]
        assert layer["x"] == focused["x"] + round((focused["width"] / scale - indicator.WIDTH) / 2)
        assert layer["y"] == (focused["y"] + round(focused["height"] / scale) - reserved_bottom
                              - indicator.BOTTOM_MARGIN - indicator.HEIGHT)
        assert hyprland.active_window().get("address") == in_front
        shown.show(State.WORKING)
        time.sleep(0.3)
        shown.show(None)
        assert _wait_for(lambda: not _pill_layers())
    finally:
        shown.stop()


def test_the_overlay_only_starts_once_the_pill_shows():
    window = _window()
    try:
        window.pump()
        window.present(indicator._draw(State.LISTENING, [0.0] * indicator.BAR_COUNT, 0, window.size, window.scale),
                       0.0)
        assert window._overlay is None  # a pill switched off never shows, so its overlay never runs
    finally:
        window.close()


@needs_hyprland
def test_the_overlay_closes_with_ghostwriter():
    window = _window()
    _show(window)
    assert _wait_for(window._ready.is_set)
    overlay = window._overlay
    window.close()
    assert overlay.poll() is not None


def test_a_new_screen_scale_changes_the_size_and_scale_together_between_frames():
    window = _window()
    window._scales.put(1.5)
    window._scales.put(2.0)
    assert window.scale == 1.0
    window.pump()
    assert (window.scale, window.size) == (2.0, (2 * indicator.WIDTH, 2 * indicator.HEIGHT))
    window.close()


def test_without_overlay_layers_the_pill_shows_nothing_and_says_so_once(monkeypatch, caplog):
    if not os.environ.get("DISPLAY"):
        pytest.skip("needs X11 or XWayland to stand in for a desktop without overlay layers")
    monkeypatch.setenv("GDK_BACKEND", "x11")  # X11 has no layer shell, like GNOME
    caplog.set_level("INFO", logger="ghostwriter")
    window = _window()
    try:
        _show(window)
        assert _wait_for(lambda: window._never)
        assert _wait_for(lambda: window._overlay.poll() is not None)
        for _ in range(3):
            _show(window)
        assert not window.visible and window._overlay is None  # and it isn't started again
        assert caplog.text.count("no overlay layers") == 1 and "quit" not in caplog.text
    finally:
        window.close()


def test_without_layer_shell_installed_the_log_names_whats_missing(monkeypatch, caplog):
    monkeypatch.setattr(pill, "OVERLAY", [
        sys.executable, "-c",
        "import sys\nfrom ghostwriter.linux import pill_overlay as overlay\n"
        "overlay.LAYER_SHELL_LIBRARY = 'libnot-there.so.0'\noverlay.main(*map(int, sys.argv[1:4]))"])
    window = _window()
    try:
        _show(window)
        assert _wait_for(lambda: window._never)
        _show(window)
        assert "needs gtk4-layer-shell" in caplog.text and "libnot-there.so.0" in caplog.text
        assert "quit" not in caplog.text
    finally:
        window.close()


def test_an_overlay_that_quits_starts_again_a_few_times_then_stays_off(monkeypatch, caplog):
    # Says it's ready, then quits at the first frame, like an overlay whose screen connection dropped.
    monkeypatch.setattr(pill, "OVERLAY", [
        sys.executable, "-c", "import sys\nprint('ready', flush=True)\nsys.stdin.buffer.read(1)"])
    monkeypatch.setattr(pill, "RESTART_DELAY", 0)
    window = _window()
    try:
        assert _wait_for(lambda: (_show(window), window._never)[1], seconds=15)
        assert caplog.text.count("starts again on the next dictation") == pill.MAX_RESTARTS
        assert caplog.text.count("keeps quitting") == 1
    finally:
        window.close()
