"""Ghostwriter as Omarchy's dictation app, picked in Omarchy's menu under Setup > Defaults > Dictation.

Omarchy owns the dictation keys there: holding Right Alt runs `omarchy-dictation start`, letting go runs `stop`, and
Alt + Space runs `toggle`. Those run the chosen app's adapter, omarchy-dictation-ghostwriter, which passes each one
to the running Ghostwriter as a signal (or starts Ghostwriter in the bar if it isn't running). While Omarchy has
Ghostwriter picked, the hotkey reader takes those signals instead of reading the keyboard itself.

`python -m ghostwriter.linux.shortcuts` adds the three commands below and the menu row.
"""

import os
import shlex
import shutil
import signal
from pathlib import Path

from ghostwriter.paths import PROJECT

BACKEND = "ghostwriter"  # the name Omarchy knows Ghostwriter by
HOLD_KEY = "Right Alt"
TOGGLE_KEY = "Alt + Space"
MENU_PLACE = "Setup > Defaults > Dictation"
MENU_ROW = f"setup.default.dictation.{BACKEND}"
MADE_BY = "# Made by Ghostwriter; it's rewritten when Ghostwriter sets up its launcher entry."
# What each dictation command sends the running Ghostwriter.
SIGNALS = {"start": signal.SIGUSR1, "stop": signal.SIGUSR2, "toggle": signal.SIGRTMIN}


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def bin_folder() -> Path:
    """Where Omarchy, like most desktops, puts the user's own commands on the PATH."""
    return Path.home() / ".local" / "bin"


def backend_path() -> Path:
    return config_home() / "omarchy" / "defaults" / "dictation"


def menu_path() -> Path:
    return config_home() / "omarchy" / "extensions" / "omarchy-menu.jsonc"


def owns_keys() -> bool:
    """Whether Omarchy's dictation keys run Ghostwriter right now. Omarchy only binds them while the picked app's own
    command and its adapter are installed, so a picked but missing Ghostwriter leaves the keys to Ghostwriter."""
    try:
        picked = backend_path().read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return False
    return picked == BACKEND and all(shutil.which(command) for command in (BACKEND, "omarchy-dictation",
                                                                           f"omarchy-dictation-{BACKEND}"))


def keys(uses_altgr: bool) -> dict[str, str | None]:
    """Omarchy's dictation keys, for the app window and the bar's panel. A layout with AltGr on Right Alt sends a
    different key there, which Omarchy's hold binding doesn't match, so only Alt + Space works."""
    return {"desktop": "Omarchy", "hold": None if uses_altgr else HOLD_KEY, "toggle": TOGGLE_KEY, "change": MENU_PLACE}


def add_commands(folder: Path | None = None) -> list[Path]:
    """Add `ghostwriter`, Omarchy's adapter for it, and its installer, leaving alone any file by those names that
    Ghostwriter didn't make."""
    folder = folder or bin_folder()
    commands = {
        BACKEND: _LAUNCHER.format(made_by=MADE_BY, project=shlex.quote(str(PROJECT))),
        f"omarchy-dictation-{BACKEND}": _ADAPTER.format(
            made_by=MADE_BY, **{f"{name}_signal": number.name.removeprefix("SIG") for name, number in SIGNALS.items()}),
        f"omarchy-install-dictation-{BACKEND}": _INSTALLER.format(made_by=MADE_BY),
    }
    added = []
    for name, text in commands.items():
        path = folder / name
        if path.exists() and MADE_BY not in path.read_text(encoding="utf-8", errors="replace"):
            continue
        folder.mkdir(parents=True, exist_ok=True)
        draft = path.with_name(f".{name}.new")
        draft.write_text(text, encoding="utf-8")
        draft.chmod(0o755)
        draft.replace(path)
        added.append(path)
    return added


def add_menu_row(path: Path | None = None) -> bool:
    """Add Ghostwriter to Omarchy's list of dictation apps. Omarchy's own list is fixed, so the row goes in the
    user's menu extensions file, which Omarchy merges in. False when it's already there."""
    path = path or menu_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = "{\n}\n"
    if f'"{MENU_ROW}"' in text:
        return False
    opening = text.find("{")
    if opening < 0:
        raise ValueError(f"{path} isn't a menu extensions file")
    # Right after the opening brace, with a trailing comma, which Omarchy's menu files allow.
    text = text[: opening + 1] + "\n  " + _MENU_ROW + "," + text[opening + 1:]
    path.parent.mkdir(parents=True, exist_ok=True)
    draft = path.with_name(path.name + ".new")
    draft.write_text(text, encoding="utf-8")
    draft.replace(path)
    return True


_MENU_ROW = (
    f'"{MENU_ROW}": {{"icon":"\U000f02a0","label":"Ghostwriter",'
    f'"checked":"[[ \\"$(omarchy-default-dictation)\\" == \\"{BACKEND}\\" ]]",'
    f'"when":"omarchy-cmd-present omarchy-install-dictation-{BACKEND}",'
    f'"action":"omarchy-default-dictation {BACKEND}"}}'
)

_LAUNCHER = """#!/bin/bash
# Starts Ghostwriter: opens its window, or with --tray just the ghost in the bar.
{made_by}
cd -- {project} || exit 1
exec .venv/bin/python -m ghostwriter "$@"
"""

_ADAPTER = """#!/bin/bash
# omarchy:summary=Record dictation using Ghostwriter
# omarchy:args=<start|stop|toggle>
{made_by}

case "${{1:-}}" in
  start) signal={start_signal} ;;
  stop) signal={stop_signal} ;;
  toggle) signal={toggle_signal} ;;
  *) echo "Usage: omarchy dictation ghostwriter <start|stop|toggle>" >&2; exit 1 ;;
esac

state_folder="${{XDG_STATE_HOME:-$HOME/.local/state}}/ghostwriter"

# The running Ghostwriter, from the status file it keeps for Omarchy's panel, checked against the process itself
# since a stale file can name a process that has since ended or been reused.
running() {{
  local pid state
  read -r pid state < <(jq -r '"\\(.pid) \\(.state)"' "$state_folder/status.json" 2>/dev/null)
  if [[ $pid =~ ^[0-9]+$ && $state != stopped && $(tr '\\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null) == *"-m ghostwriter "* ]]; then
    echo "$pid"
  else
    pgrep -u "$UID" -n -f -- '-m ghostwriter( |$)'
  fi
}}

if pid=$(running); then
  kill -s "$signal" "$pid"
  exit
fi
[[ $1 == stop ]] && exit 0

# Not running: start it in the bar. This press is lost while it loads, and presses during the next minute don't
# start a second copy.
starting="$state_folder/starting"
if [[ -n $(find "$starting" -mmin -1 2>/dev/null) ]]; then
  exit 0
fi
mkdir -p "$state_folder"
touch "$starting"
if command -v uwsm-app >/dev/null; then
  setsid -f uwsm-app -- ghostwriter --tray >/dev/null 2>&1
else
  setsid -f ghostwriter --tray >/dev/null 2>&1
fi
"""

_INSTALLER = """#!/bin/bash
# omarchy:summary=Use Ghostwriter for dictation
{made_by}

set -e

omarchy-dictation-use ghostwriter
omarchy-restart-hyprctl
# Started now if it isn't running, so the first press already dictates.
if ! pgrep -u "$UID" -f -- '-m ghostwriter( |$)' >/dev/null; then
  setsid -f uwsm-app -- ghostwriter --tray >/dev/null 2>&1
fi
omarchy-notification-send -g "Ghostwriter Dictation Ready" "$(omarchy-i18n dictation.hint)" -t 10000
"""
