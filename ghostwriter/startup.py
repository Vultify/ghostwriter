"""What the tray app is doing as it starts, kept in startup.json so the app window (a separate program) can show
the speech model's first download.

The "model" field is downloading (with "done" and "total" bytes), loading, ready, or failed.
"""

import json
from pathlib import Path

from ghostwriter.paths import STARTUP_PATH


def write(path: Path = STARTUP_PATH, **status) -> None:
    try:
        path.write_text(json.dumps(status), encoding="utf-8")
    except OSError:
        pass  # the window keeps showing the last status it read


def read(path: Path = STARTUP_PATH) -> dict:
    """The latest status, or an empty one if the file is missing or caught halfway through a write."""
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return status if isinstance(status, dict) else {}
