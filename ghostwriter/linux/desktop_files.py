"""Reading app launcher entries (.desktop files), which hold each app's everyday name."""

import functools
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DesktopFile:
    id: str  # the file name without .desktop, which apps usually reuse as their window's app id
    name: str
    command: str
    window_class: str  # StartupWMClass, for apps whose app id differs from the file name


def find(app_id: str) -> DesktopFile | None:
    """The launcher entry for an app id, matched by file name or window class, ignoring case."""
    wanted = app_id.lower()
    if not wanted:
        return None
    return next((entry for entry in installed() if wanted in (entry.id.lower(), entry.window_class.lower())), None)


def opening(address: str) -> DesktopFile | None:
    """The launcher entry whose command opens a web address, like a web app for "web.whatsapp.com"."""
    return next((entry for entry in installed() if f"//{address}" in entry.command), None)


@functools.cache
def installed() -> tuple[DesktopFile, ...]:
    """Every launcher entry, with the user's own ahead of the system's so theirs win."""
    entries, seen = [], set()
    for folder in _application_folders():
        for path in sorted(folder.glob("*.desktop")):
            if path.stem not in seen and (entry := _read(path)):
                seen.add(path.stem)
                entries.append(entry)
    return tuple(entries)


def _application_folders() -> list[Path]:
    home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    shared = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [Path(folder) / "applications" for folder in [home, *shared.split(":")] if folder]


def _read(path: Path) -> DesktopFile | None:
    fields, section = {}, None
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[Desktop Entry]" and "=" in line:
            key, value = line.split("=", 1)
            fields.setdefault(key.strip(), value.strip())
    if not fields.get("Name"):
        return None
    return DesktopFile(path.stem, fields["Name"], fields.get("Exec", ""), fields.get("StartupWMClass", ""))
