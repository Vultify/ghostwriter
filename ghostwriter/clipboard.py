"""Save, write, and restore the Windows clipboard, keeping Ghostwriter's own writes out of clipboard history."""

import ctypes
import time
from collections.abc import Iterator
from contextlib import contextmanager

from ghostwriter import win32
from ghostwriter.win32 import kernel32, user32

Snapshot = list[tuple[int, bytes]]

# Formats that hold GDI handles or are copies Windows builds on its own from the formats we do keep.
_SKIPPED_FORMATS = {1, 2, 3, 7, 9, 14, 0x80, 0x82, 0x83, 0x8E}
_PRIVATE_AND_GDI_RANGE = range(0x200, 0x400)
_SKIPPED_NAMES = {"Ole Private Data", "DataObject", "OleClipboardPersistOnFlush"}
_FIRST_REGISTERED_FORMAT = 0xC000

# Windows clipboard history and clipboard managers skip anything tagged with these.
_HISTORY_OPT_OUT_NAMES = (
    "ExcludeClipboardContentFromMonitorProcessing",
    "CanIncludeInClipboardHistory",
    "CanUploadToCloudClipboard",
)
_OPT_OUT_VALUE = b"\x00\x00\x00\x00"

_OPEN_ATTEMPTS = 20
_OPEN_RETRY_SECONDS = 0.02


class ClipboardError(RuntimeError):
    pass


class Clipboard:
    def __init__(self) -> None:
        # A hidden window to own our clipboard writes; Windows rejects writes made without an owner.
        self._window = user32.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, win32.HWND_MESSAGE, None, None, None)
        self._opt_out_formats = [user32.RegisterClipboardFormatW(name) for name in _HISTORY_OPT_OUT_NAMES]

    def snapshot(self) -> Snapshot:
        """Copy every format on the clipboard that can be put back later, in its original order."""
        formats = []
        with self._open():
            fmt = user32.EnumClipboardFormats(0)
            while fmt:
                if self._can_restore(fmt) and (data := self._read(fmt)) is not None:
                    formats.append((fmt, data))
                fmt = user32.EnumClipboardFormats(fmt)
        return formats

    def write_text(self, text: str) -> int:
        """Put text on the clipboard and return the clipboard's change counter right after the write."""
        with self._open():
            self._replace([(win32.CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))])
        # Read after closing: Windows adds a locale format on close, which counts as one more change.
        return user32.GetClipboardSequenceNumber()

    def restore(self, snapshot: Snapshot, expected_sequence: int) -> bool:
        """Put a snapshot back, unless something else changed the clipboard after our write."""
        with self._open():
            if user32.GetClipboardSequenceNumber() != expected_sequence:
                return False
            self._replace(snapshot)
            return True

    @contextmanager
    def _open(self) -> Iterator[None]:
        for _ in range(_OPEN_ATTEMPTS):
            if user32.OpenClipboard(self._window):
                break
            time.sleep(_OPEN_RETRY_SECONDS)
        else:
            raise ClipboardError("Another app is holding the clipboard open")
        try:
            yield
        finally:
            user32.CloseClipboard()

    def _replace(self, formats: Snapshot) -> None:
        if not user32.EmptyClipboard():
            raise ClipboardError("Could not empty the clipboard")
        for fmt, data in formats:
            self._write(fmt, data)
        for fmt in self._opt_out_formats:
            self._write(fmt, _OPT_OUT_VALUE)

    def _can_restore(self, fmt: int) -> bool:
        if fmt in _SKIPPED_FORMATS or fmt in _PRIVATE_AND_GDI_RANGE or fmt in self._opt_out_formats:
            return False
        if fmt >= _FIRST_REGISTERED_FORMAT:
            name = ctypes.create_unicode_buffer(256)
            user32.GetClipboardFormatNameW(fmt, name, len(name))
            return name.value not in _SKIPPED_NAMES
        return True

    @staticmethod
    def _read(fmt: int) -> bytes | None:
        handle = user32.GetClipboardData(fmt)
        size = kernel32.GlobalSize(handle) if handle else 0
        pointer = kernel32.GlobalLock(handle) if size else None
        if not pointer:
            return None
        try:
            return ctypes.string_at(pointer, size)
        finally:
            kernel32.GlobalUnlock(handle)

    @staticmethod
    def _write(fmt: int, data: bytes) -> None:
        handle = kernel32.GlobalAlloc(win32.GMEM_MOVEABLE, len(data))
        pointer = kernel32.GlobalLock(handle) if handle else None
        if not pointer:
            raise ClipboardError("Out of memory for clipboard data")
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(fmt, handle):
            kernel32.GlobalFree(handle)
            raise ClipboardError(f"Could not write clipboard format {fmt}")
