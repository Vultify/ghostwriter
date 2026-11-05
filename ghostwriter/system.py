"""The parts of Ghostwriter that work differently on each operating system, loaded for the one it's running on.

Every system's package has the same modules with the same names in them:
  app_window   starting, finding, and framing the app window
  desktop      opening files, message boxes, one copy at a time, light or dark theme, sounds
  hotkey       the keys to pick from, and the hook that reports the hotkey and hides it from other apps
  install      the install command and the updater
  microphones  the mics to pick from
  paster       pasting into the app in front, and naming that app for History
  pill         the window the listening pill is drawn in
  processes    starting helper programs that close when Ghostwriter does
  shortcuts    the app menu entry and starting at login

Each module loads the first time it's used, so a program only loads the parts it needs.
"""

import importlib
import sys

PACKAGE = "ghostwriter.windows" if sys.platform == "win32" else "ghostwriter.linux"
MODULES = ("app_window", "desktop", "hotkey", "install", "microphones", "paster", "pill", "processes", "shortcuts")

__all__ = list(MODULES)


def __getattr__(name: str):
    if name not in MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f"{PACKAGE}.{name}")
    globals()[name] = module  # later lookups find it directly
    return module
