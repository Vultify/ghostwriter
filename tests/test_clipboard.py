"""The clipboard round trip: save it, write our text, and put the original back."""

from conftest import text_of

from ghostwriter import win32
from ghostwriter.clipboard import Clipboard
from ghostwriter.win32 import user32

HTML = "Version:0.9\r\nStartHTML:0\r\nEndHTML:0\r\n<b>bold</b>".encode() + b"\0"


def _put(clipboard: Clipboard, text: str, html: bytes | None = None) -> None:
    formats = [(win32.CF_UNICODETEXT, (text + "\0").encode("utf-16-le"))]
    if html:
        formats.append((user32.RegisterClipboardFormatW("HTML Format"), html))
    clipboard.restore(formats, user32.GetClipboardSequenceNumber())


def test_snapshot_keeps_every_restorable_format():
    clipboard = Clipboard()
    _put(clipboard, "original", HTML)
    snapshot = clipboard.snapshot()
    html_format = user32.RegisterClipboardFormatW("HTML Format")
    assert text_of(snapshot) == "original"
    assert dict(snapshot)[html_format].startswith(HTML)


def test_write_then_restore_puts_the_original_back():
    clipboard = Clipboard()
    _put(clipboard, "original", HTML)
    before = clipboard.snapshot()
    sequence = clipboard.write_text("dictated words")
    assert text_of(clipboard.snapshot()) == "dictated words"
    assert clipboard.restore(before, sequence)
    after = clipboard.snapshot()
    assert text_of(after) == "original"
    assert user32.RegisterClipboardFormatW("HTML Format") in dict(after)


def test_our_writes_are_tagged_to_stay_out_of_clipboard_history():
    clipboard = Clipboard()
    clipboard.write_text("private")
    tagged = set()
    fmt = 0
    user32.OpenClipboard(None)
    try:
        while fmt := user32.EnumClipboardFormats(fmt):
            tagged.add(fmt)
    finally:
        user32.CloseClipboard()
    for name in ("ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory"):
        assert user32.RegisterClipboardFormatW(name) in tagged


def test_restore_is_skipped_when_the_user_copies_something_new():
    clipboard = Clipboard()
    _put(clipboard, "original")
    before = clipboard.snapshot()
    sequence = clipboard.write_text("dictated words")
    _put(clipboard, "something the user copied")
    assert not clipboard.restore(before, sequence)
    assert text_of(clipboard.snapshot()) == "something the user copied"
