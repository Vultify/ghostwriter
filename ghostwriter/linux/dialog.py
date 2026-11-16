"""A message box for the tray app, run as a small program of its own:

    python -m ghostwriter.linux.dialog error|question TEXT

It exits with 0 when the answer is yes, or once an error has been seen.
"""

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

TITLE = "Ghostwriter"


def main(kind: str, text: str) -> int:
    # The first paragraph is the heading and the rest goes under it, like a Windows message box's text.
    heading, _, details = text.partition("\n\n")
    question = kind == "question"
    dialog = Gtk.MessageDialog(
        message_type=Gtk.MessageType.QUESTION if question else Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.YES_NO if question else Gtk.ButtonsType.OK,
        text=heading,
        title=TITLE,
    )
    if details:
        dialog.format_secondary_text(details)
    dialog.set_keep_above(True)
    answer = dialog.run()
    return 0 if answer in (Gtk.ResponseType.YES, Gtk.ResponseType.OK) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
