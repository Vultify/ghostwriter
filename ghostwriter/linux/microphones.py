"""The mics to pick from on Linux, as PipeWire lists them, so the names match the desktop's sound settings.

Recordings go through PipeWire's ALSA plugin, which records from the system default unless PIPEWIRE_NODE names a
mic when the recording opens. Ghostwriter sets it just for that moment. A mic that's gone falls back to the system
default in PipeWire itself."""

import contextlib
import json
import logging
import os
import subprocess
import threading
from collections.abc import Iterator

from ghostwriter.linux import desktop

_TARGET = "PIPEWIRE_NODE"
_MIC_CLASSES = ("Audio/Source", "Audio/Source/Virtual")  # mics, and virtual ones like noise suppression
# Added once here, while Ghostwriter starts, and later only changed in place: adding a variable while other threads
# read the environment isn't safe, changing one's value is. "-1" is PipeWire's word for the system default, and a
# value the user set themselves stays the default.
_SYSTEM_DEFAULT = os.environ.setdefault(_TARGET, "-1")
_target_lock = threading.Lock()
_nodes: dict[str, str] = {}  # the last list found, so a recording doesn't wait on PipeWire each time

log = logging.getLogger("ghostwriter")


def microphones() -> dict[str, str]:
    """Map each mic's name to its PipeWire node name. Empty without PipeWire, so only the system default is offered."""
    global _nodes
    try:
        objects = json.loads(subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=5,
                                            check=True).stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    found = {}
    for item in objects:
        properties = (item.get("info") or {}).get("props") or {}
        if item.get("type") != "PipeWire:Interface:Node" or properties.get("media.class") not in _MIC_CLASSES:
            continue
        name = properties.get("node.description") or properties.get("node.nick") or properties["node.name"]
        label, number = name, 2
        while label in found:  # two of the same mic
            label, number = f"{name} ({number})", number + 1
        found[label] = properties["node.name"]
    _nodes = found
    return found


@contextlib.contextmanager
def recording_from(microphone: str | None) -> Iterator[None]:
    """Point a recording opened inside this block at a mic, or at the system default for None. The device to open is
    always the default one; PipeWire does the picking."""
    node = _SYSTEM_DEFAULT if microphone is None else _node(microphone)
    with _target_lock:
        os.environ[_TARGET] = node
        try:
            yield None
        finally:
            os.environ[_TARGET] = _SYSTEM_DEFAULT  # programs Ghostwriter starts get the default


def _node(microphone: str) -> str:
    node = _nodes.get(microphone) or microphones().get(microphone)
    if node is None:
        log.warning("Mic %r isn't connected, using the %s default", microphone, desktop.NAME)
        return _SYSTEM_DEFAULT
    return node
