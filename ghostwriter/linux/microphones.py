"""The mics to pick from on Linux. For now Ghostwriter records from the system's default mic, which the desktop's
sound settings choose, and picking one in Ghostwriter comes in a later step."""


def microphones() -> dict[str, int]:
    """No mics to pick from yet, so the menu only offers the system default."""
    return {}
