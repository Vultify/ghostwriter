"""Installing and updating on Linux. Both come with get.sh, a later step of the Linux port. Until then every Linux
copy is a git checkout, which updates with git pull and builds its speech engine with this script."""

from pathlib import Path

INSTALL_COMMAND = "bash scripts/build_whisper_cpp.sh"


def start_update(folder: Path) -> None:
    raise NotImplementedError("Updating a Linux install comes with get.sh")
