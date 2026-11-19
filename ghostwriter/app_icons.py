"""The icons of the apps dictated into, shown next to each dictation on Home and in History.

The tray app saves an app's icon the first time it pastes into it, as a small PNG named after the app; the window
reads them back. An app without a saved icon shows its first letter instead.
"""

import base64
import hashlib
import logging
import time
from pathlib import Path

from ghostwriter.paths import APP_ICONS_DIR

OWN_NAME = "Ghostwriter"  # the window draws its own ghost for these

RETRY_SECONDS = 3600  # how long an app that gave no icon goes before it's asked again
log = logging.getLogger("ghostwriter")
# Programs that gave no icon, and when, so they aren't looked up on every dictation. Keyed by the program, since two
# programs can share a name.
_without_icon: dict[str, float] = {}


def remember(name: str, app, folder: Path = APP_ICONS_DIR) -> None:
    """Save an app's icon if it isn't saved yet. Never raises: a missing icon only costs the picture."""
    path = _path(name, folder)
    program = str(getattr(app, "program", app))
    if name == OWN_NAME or app is None or path.exists():
        return
    if time.monotonic() - _without_icon.get(program, -RETRY_SECONDS) < RETRY_SECONDS:
        return
    from ghostwriter.system import paster  # only the tray app saves icons; the window just reads them

    try:
        png = paster.app_icon(app)
    except Exception:
        log.warning("Couldn't save the icon for %s", name, exc_info=True)
        png = None
    if png:
        folder.mkdir(exist_ok=True)
        path.write_bytes(png)
    else:
        _without_icon[program] = time.monotonic()


def data_urls(names: list[str], folder: Path = APP_ICONS_DIR) -> dict[str, str]:
    """The saved icons of these apps, ready for an <img>. Apps without one are left out."""
    found = {}
    for name in set(names):
        try:
            png = _path(name, folder).read_bytes()
        except OSError:
            continue
        found[name] = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return found


def _path(name: str, folder: Path) -> Path:
    # Hashed, since app names can hold characters a file name can't.
    return folder / (hashlib.sha256(name.encode("utf-8")).hexdigest()[:20] + ".png")
