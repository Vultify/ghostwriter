"""Installing and updating on Windows, which get.ps1 does in PowerShell."""

import os
import subprocess
from pathlib import Path

from ghostwriter.windows.processes import NEW_CONSOLE

INSTALL_COMMAND = "irm https://raw.githubusercontent.com/Vultify/ghostwriter/main/get.ps1 | iex"


def start_update(folder: Path) -> None:
    """Open a PowerShell window that runs get.ps1 on this folder; it closes Ghostwriter, updates, and restarts it."""
    command = f"{INSTALL_COMMAND}; Read-Host 'Press Enter to close this window'"
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        env={**os.environ, "GHOSTWRITER_HOME": str(folder)},
        creationflags=NEW_CONSOLE,
    )
