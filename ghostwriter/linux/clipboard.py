"""Save, write, and restore the Wayland clipboard with wl-clipboard, keeping Ghostwriter's own writes out of clipboard
history."""

import subprocess
from dataclasses import dataclass

TEXT = "text/plain;charset=utf-8"
# Clipboard history, Omarchy's included, skips anything offered with this type. It's how password managers copy.
SENSITIVE = "x-kde-passwordManagerHint"

_TEXT_TYPES = (TEXT, "text/plain", "UTF8_STRING", "STRING", "TEXT")
_TIMEOUT_SECONDS = 2.0  # the app that copied something hands it over, and a frozen one never would


class ClipboardError(RuntimeError):
    pass


@dataclass(frozen=True)
class Snapshot:
    """What was on the clipboard, in one format. wl-copy offers one format at a time, so formatted text from a browser
    comes back as plain text, and an image as the image."""

    mime: str
    data: bytes


class Clipboard:
    def snapshot(self) -> Snapshot | None:
        """The clipboard's most useful format, or None when it's empty."""
        types = self._types()
        mime = _best_type(types)
        return Snapshot(mime, self._read(mime)) if mime else None

    def write_text(self, text: str) -> str:
        """Put text on the clipboard, marked so clipboard history skips it, and return what was written."""
        self._copy(TEXT, text.encode())
        return text

    def restore(self, snapshot: Snapshot | None, written: str) -> bool:
        """Put a snapshot back, unless something else changed the clipboard after our write."""
        types = self._types()
        if not (SENSITIVE in types and TEXT in types and self._read(TEXT) == written.encode()):
            return False
        self.replace(snapshot)
        return True

    def replace(self, snapshot: Snapshot | None) -> None:
        """Put a snapshot on the clipboard no matter what's there now. It's marked for history to skip too, since
        history already has it from when it was first copied."""
        if snapshot is None:
            _run(["wl-copy", "--clear"])
        else:
            self._copy(TEXT if snapshot.mime in _TEXT_TYPES else snapshot.mime, snapshot.data)

    @staticmethod
    def _types() -> list[str]:
        result = _run(["wl-paste", "--list-types"], capture=True, check=False)
        return result.stdout.decode(errors="replace").split("\n") if result.returncode == 0 else []

    @staticmethod
    def _read(mime: str) -> bytes:
        return _run(["wl-paste", "--no-newline", "--type", mime], capture=True).stdout

    @staticmethod
    def _copy(mime: str, data: bytes) -> None:
        # wl-copy hands the clipboard to a copy of itself that keeps serving it in the background, so it's started in
        # its own session to outlive Ghostwriter, and with no pipes for that copy to hold open.
        _run(["wl-copy", "--type", mime, "--sensitive"], data=data, new_session=True)


def _best_type(types: list[str]) -> str | None:
    """An image if there is one, then plain text, then whatever the app listed first."""
    offered = [mime for mime in types if mime and mime != SENSITIVE]
    return next((mime for mime in offered if mime.startswith("image/")), None) \
        or next((mime for mime in _TEXT_TYPES if mime in offered), None) \
        or next(iter(offered), None)


def _run(args: list[str], data: bytes | None = None, capture: bool = False, check: bool = True,
         new_session: bool = False) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, input=data, stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=_TIMEOUT_SECONDS, start_new_session=new_session)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ClipboardError(f"{args[0]} didn't finish: {error}") from error
    if check and result.returncode != 0:
        raise ClipboardError(f"{args[0]} failed with exit code {result.returncode}")
    return result
