"""Checking GitHub for a newer release, and handing off to get.ps1 to install it."""

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

from ghostwriter import __version__

REPO = "Vultify/ghostwriter"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
INSTALL_COMMAND = f"irm https://raw.githubusercontent.com/{REPO}/main/get.ps1 | iex"
INSTALL_DIR = Path(__file__).resolve().parent.parent


def latest_version(timeout: float = 10) -> str:
    request = urllib.request.Request(LATEST_RELEASE_URL, headers={"User-Agent": "Ghostwriter"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)["tag_name"].lstrip("v")


def is_newer(latest: str, current: str = __version__) -> bool:
    return _numbers(latest) > _numbers(current)


def is_git_checkout(folder: Path = INSTALL_DIR) -> bool:
    """A developer's copy gets updated with git, not by downloading a release over it."""
    return (folder / ".git").exists()


def start_update(folder: Path = INSTALL_DIR) -> None:
    """Open a PowerShell window that runs get.ps1 on this folder; it closes Ghostwriter, updates, and restarts it."""
    command = f"{INSTALL_COMMAND}; Read-Host 'Press Enter to close this window'"
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        env={**os.environ, "GHOSTWRITER_HOME": str(folder)},
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def _numbers(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version)[:3])
