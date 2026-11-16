"""The listening pill's window on Linux comes in a later step (a Wayland overlay), so for now it shows nothing."""

from PIL import Image


class PillWindow:
    """Takes each frame ghostwriter.indicator draws and shows none of them."""

    def __init__(self, width: int, height: int, bottom_margin: int) -> None:
        self.scale = 1.0
        self.size = (width, height)
        self.visible = False

    def pump(self) -> None:
        pass

    def present(self, image: Image.Image, opacity: float) -> None:
        pass

    def close(self) -> None:
        pass
