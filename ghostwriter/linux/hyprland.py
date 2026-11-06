"""Talking to Hyprland, the desktop Omarchy runs on, through the control socket hyprctl uses."""

import json
import os
import socket
from pathlib import Path

_TIMEOUT_SECONDS = 2.0

# Hyprland lets go of the keys on its own timer, so they can't stay stuck even if Ghostwriter stops in between. This
# down, wait, up pattern is how Omarchy's own paste shortcut presses keys.
_PRESS_KEYS = """
local keys = {{ mods = {mods}, key = {key} }}
hl.dispatch(hl.dsp.send_key_state({{ mods = keys.mods, key = keys.key, state = "down" }}))
hl.timer(function()
  hl.dispatch(hl.dsp.send_key_state({{ mods = keys.mods, key = keys.key, state = "up" }}))
end, {{ timeout = 50, type = "oneshot" }})
"""


class HyprlandError(RuntimeError):
    pass


def running() -> bool:
    return bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))


def request(command: str) -> str:
    """Send one hyprctl command, like "j/activewindow", and return Hyprland's reply."""
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not signature:
        raise HyprlandError("Hyprland isn't running")
    path = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"), "hypr", signature, ".socket.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(_TIMEOUT_SECONDS)
        connection.connect(str(path))
        connection.sendall(command.encode())
        reply = b"".join(iter(lambda: connection.recv(65536), b""))
    return reply.decode(errors="replace")


def active_window() -> dict:
    """The window in front (class, title, pid, tags, and more), or an empty dict when there isn't one."""
    return json.loads(request("j/activewindow") or "{}")


def option(name: str) -> str:
    """A text setting, like "input:kb_layout"."""
    return json.loads(request(f"j/getoption {name}")).get("str", "")


def press_keys(mods: str, key: str) -> None:
    """Press and release a shortcut, like mods "CTRL" and key "V", in the app in front."""
    reply = request("eval " + _PRESS_KEYS.format(mods=json.dumps(mods), key=json.dumps(key)))
    if reply.strip() != "ok":
        raise HyprlandError(reply.strip())
