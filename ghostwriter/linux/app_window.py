"""The app window's Linux parts: starting it, finding it, and bringing it to the front. The page is shown in
WebKitGTK, and the desktop draws the frame (or none, on tiling desktops like Omarchy), so the page hides its own
Windows-style title bar."""

import json
import logging
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

from gi.repository import GLib

from ghostwriter.linux import hyprland
from ghostwriter.linux.shortcuts import APP_ID
from ghostwriter.paths import PROJECT

WEB_ENGINE = "gtk"  # pywebview's name for WebKitGTK
OWN_FRAME = False  # the desktop frames the window, not the page
MISSING_ENGINE_MESSAGE = (
    "Ghostwriter's window needs WebKitGTK (webkit2gtk-4.1), and it isn't installed.\n\n"
    "Dictation still works: use the ghost in the bar."
)
_WINDOW_MODULE = "ghostwriter.window"
WIDTH, HEIGHT = 1360, 920  # the window's size, as on Windows
MIN_WIDTH, MIN_HEIGHT = 940, 640  # the smallest the page fits in, as window.py tells GTK
SCREEN_MARGIN = 40  # kept free around a floating window on a screen too small for the full size
TITLE = "Ghostwriter"  # the window's title, as window.py sets it
DIALOG_TITLES = "^(Open|Save) file$"  # pywebview's file dialogs, for Import and Export
DIALOG_WIDTH, DIALOG_HEIGHT = 875, 600  # the size Omarchy gives file dialogs that come through the desktop portal
DIALOG_MIN_WIDTH, DIALOG_MIN_HEIGHT = 600, 400
# Floats the window centered at its size, like Omarchy does for LocalSend. Set again before every launch, replacing
# the last one, the way Omarchy's own About window sets its rule, so nothing is added to the Hyprland config.
# The file dialogs get a rule of their own: GTK opens them directly rather than through the portal, so Omarchy's
# file dialog rule never sees them, and GTK's own size can be taller than a small screen.
_FLOAT_RULE = """
if ghostwriter_window_rule then ghostwriter_window_rule:set_enabled(false) end
if ghostwriter_dialog_rule then ghostwriter_dialog_rule:set_enabled(false) end
ghostwriter_window_rule = hl.window_rule({{ match = {{ class = {app_id}, title = {title} }},
  float = true, center = true, size = {{ {width}, {height} }} }})
ghostwriter_dialog_rule = hl.window_rule({{ match = {{ class = {app_id}, title = {dialog_titles} }},
  float = true, center = true, size = {{ {dialog_width}, {dialog_height} }} }})
"""

log = logging.getLogger("ghostwriter")

# The window's app id, which desktops use to name it and match it to its launcher entry. It has to be set before
# GTK starts, and this module loads before the window imports GTK.
GLib.set_prgname(APP_ID)


def open_window() -> None:
    """Start the app window as its own program. A second start brings the open one to the front instead."""
    # With a window already open, the new start only brings it to the front, and replacing the rule could change
    # the open window's size.
    if hyprland.running() and not _window_processes():
        _float_on_hyprland()
    subprocess.Popen([sys.executable, "-m", _WINDOW_MODULE], cwd=PROJECT, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def close_window(title: str) -> None:
    for pid in _window_processes():
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def bring_to_front(title: str) -> None:
    """Focus the open window. Wayland doesn't let an app raise itself, so this asks Hyprland, the way Omarchy's own
    launch-or-focus does; other desktops leave it where it is."""
    if not hyprland.running():
        return
    for pid in _window_processes():
        target = json.dumps(f"pid:{pid}")
        try:
            if hyprland.request(f"dispatch hl.dsp.focus({{ window = {target} }})").strip() != "ok":
                hyprland.request(f"dispatch focuswindow pid:{pid}")
        except (OSError, hyprland.HyprlandError) as error:
            log.warning("Couldn't bring the window to the front: %s", error)


def _float_on_hyprland() -> None:
    """Hyprland tiles windows by default, which squeezes this one; float it instead, shrunk to fit small screens."""
    try:
        screen = next(monitor for monitor in json.loads(hyprland.request("j/monitors")) if monitor["focused"])
        left, top, right, bottom = screen["reserved"]  # the bar's space
        free_width = screen["width"] / screen["scale"] - left - right - 2 * SCREEN_MARGIN
        free_height = screen["height"] / screen["scale"] - top - bottom - 2 * SCREEN_MARGIN
        width = max(MIN_WIDTH, min(WIDTH, free_width))
        height = max(MIN_HEIGHT, min(HEIGHT, free_height))
        rule = _FLOAT_RULE.format(app_id=json.dumps(f"^{re.escape(APP_ID)}$"), title=json.dumps(f"^{re.escape(TITLE)}$"),
                                  width=round(width), height=round(height), dialog_titles=json.dumps(DIALOG_TITLES),
                                  dialog_width=round(max(DIALOG_MIN_WIDTH, min(DIALOG_WIDTH, free_width))),
                                  dialog_height=round(max(DIALOG_MIN_HEIGHT, min(DIALOG_HEIGHT, free_height))))
        reply = hyprland.request("eval " + rule).strip()
        if reply != "ok":
            raise hyprland.HyprlandError(reply)
    except (OSError, ValueError, KeyError, StopIteration, hyprland.HyprlandError) as error:
        log.warning("Couldn't float the window, so Hyprland tiles it: %s", error)


def style_frame(window, width: int, height: int) -> None:
    """Nothing to adjust: the desktop draws the frame."""


def _window_processes() -> list[int]:
    """The app windows running from this install, found by their command line and folder."""
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if not _runs_module((entry / "cmdline").read_bytes().split(b"\0"), _WINDOW_MODULE):
                continue
            folder = Path(os.readlink(entry / "cwd"))
        except OSError:  # gone already, or someone else's
            continue
        if folder == PROJECT:
            found.append(int(entry.name))
    return found


def _runs_module(command: list[bytes], module: str) -> bool:
    arguments = [part.decode(errors="replace") for part in command]
    return any(part == "-m" and following == module for part, following in zip(arguments, arguments[1:]))
