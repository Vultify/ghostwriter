"""Other apps' sound on Linux. Nothing is lowered yet: this stands in until the PipeWire version is written."""


class AppVolume:
    """One app's sound, with its own volume from 0 to 1."""

    def __init__(self, key: str, process: int) -> None:
        self.key = key  # the same for this app every time it runs, so it can be found again after a restart
        self.process = process
        self.level = 1.0


def prepare_thread() -> None:
    """Nothing to set up on Linux."""


def other_apps(playing_only: bool = True) -> list[AppVolume]:
    """No apps are found yet, so other apps keep playing at their own volume."""
    return []
