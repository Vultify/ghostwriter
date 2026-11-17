"""The listening pill on Linux: an overlay layer at the bottom center of the screen in use, which never takes the
keyboard and goes away when it's hidden or Ghostwriter closes."""

import json
import os
import sys
import time

import pytest

if sys.platform != "linux":  # skipped here rather than in conftest, like the other Linux-only files
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


@needs_hyprland
def test_the_overlay_closes_with_ghostwriter():
    window = pill.PillWindow(indicator.WIDTH, indicator.HEIGHT, indicator.BOTTOM_MARGIN)
    overlay = window._overlay
    window.close()
    assert overlay.poll() is not None


def test_without_overlay_layers_the_pill_shows_nothing_and_says_so_once(monkeypatch, caplog):
    if not os.environ.get("DISPLAY"):
        pytest.skip("needs X11 or XWayland to stand in for a desktop without overlay layers")
    monkeypatch.setenv("GDK_BACKEND", "x11")  # X11 has no layer shell, like GNOME
    caplog.set_level("INFO", logger="ghostwriter")
    window = pill.PillWindow(indicator.WIDTH, indicator.HEIGHT, indicator.BOTTOM_MARGIN)
    try:
        assert _wait_for(lambda: window._unsupported)
        frame = indicator._draw(State.LISTENING, [0.5] * indicator.BAR_COUNT, 0, window.size, window.scale)
        window.present(frame, 1.0)
        assert not window.visible
        assert caplog.text.count("no overlay layers") == 1 and "closed" not in caplog.text
    finally:
        window.close()
