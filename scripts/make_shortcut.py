"""Make Ghostwriter's app icon and add it to the Start menu, set to start with no terminal window (install.bat runs this)."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from ghostwriter.paths import ICON_PATH  # noqa: E402
from ghostwriter.shortcuts import make_shortcut, start_menu_folder  # noqa: E402
from ghostwriter.tray import draw_ghost  # noqa: E402

ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]
TILE_COLOR = (24, 24, 27, 255)
GHOST_COLOR = (255, 255, 255, 255)


def make_icon() -> None:
    """A white ghost on a dark rounded tile, so it shows up on any background."""
    size = 1024
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle((0, 0, size - 1, size - 1), radius=size * 0.22, fill=TILE_COLOR)
    ghost = draw_ghost(GHOST_COLOR, final_size=round(size * 0.72))
    tile.alpha_composite(ghost, ((size - ghost.width) // 2, (size - ghost.height) // 2 + round(size * 0.03)))
    tile.resize((256, 256), Image.LANCZOS).save(ICON_PATH, format="ICO", sizes=[(s, s) for s in ICON_SIZES])


if __name__ == "__main__":
    make_icon()
    print(f"Added Ghostwriter to the Start menu: {make_shortcut(start_menu_folder())}")
