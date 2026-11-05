"""Checking GitHub for a newer release, and handing off to the system's installer to install it."""

import json
import re
import urllib.request
from pathlib import Path

from ghostwriter import __version__
from ghostwriter.paths import PROJECT as INSTALL_DIR
from ghostwriter.system import install

REPO = "Vultify/ghostwriter"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"


def latest_version(timeout: float = 10) -> str:
    request = urllib.request.Request(LATEST_RELEASE_URL, headers={"User-Agent": "Ghostwriter"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)["tag_name"].lstrip("v")


def is_newer(latest: str, current: str | None = None) -> bool:
    return _numbers(latest) > _numbers(current or __version__)


def is_git_checkout(folder: Path = INSTALL_DIR) -> bool:
    """A developer's copy gets updated with git, not by downloading a release over it."""
    return (folder / ".git").exists()


def start_update(folder: Path = INSTALL_DIR) -> None:
    """Start the installer on this folder; it closes Ghostwriter, updates it, and starts it again."""
    install.start_update(folder)


def _numbers(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version)[:3])
