"""The program that shows the listening pill on Linux: a Wayland overlay layer (wlr-layer-shell, through
gtk4-layer-shell), the kind bars and notifications use. It never takes the keyboard, lets clicks through, and opens
on the screen in use each time it's shown. GNOME has no overlay layers, so it says so and quits there.

Ghostwriter starts it with the pill's size and bottom margin in logical pixels, sends it frames on stdin, and reads
the screen scale to draw at from its stdout. A frame is FRAME_HEADER (width and height in pixels, then 1 to show or
0 to hide) followed by width * height premultiplied BGRA pixels."""

import ctypes
import struct
import sys
import threading

FRAME_HEADER = struct.Struct("<HHB")
NAMESPACE = "ghostwriter-pill"
UNSUPPORTED = "unsupported"


def main(width: int, height: int, bottom_margin: int) -> None:
    # gtk4-layer-shell has to load before GTK does, so it can hook GTK's Wayland calls.
    ctypes.CDLL("libgtk4-layer-shell.so.0")
    import cairo
    import gi

    gi.require_version("Gdk", "4.0")
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gdk, GLib, Gtk
    from gi.repository import Gtk4LayerShell as LayerShell

    Gtk.init()
    if not LayerShell.is_supported():
        _say(UNSUPPORTED)
        return

    css = Gtk.CssProvider()
    css.load_from_string("window { background: none; }")
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    window = Gtk.Window(title="Ghostwriter", decorated=False, resizable=False)
    window.set_default_size(width, height)
    LayerShell.init_for_window(window)
    LayerShell.set_namespace(window, NAMESPACE)
    LayerShell.set_layer(window, LayerShell.Layer.OVERLAY)
    LayerShell.set_keyboard_mode(window, LayerShell.KeyboardMode.NONE)
    LayerShell.set_anchor(window, LayerShell.Edge.BOTTOM, True)
    LayerShell.set_margin(window, LayerShell.Edge.BOTTOM, bottom_margin)

    frame: dict = {}
    area = Gtk.DrawingArea(content_width=width, content_height=height)

    def draw(_area, context, _width, _height) -> None:
        if not frame:
            return
        surface = cairo.ImageSurface.create_for_data(frame["pixels"], cairo.FORMAT_ARGB32, frame["width"],
                                                     frame["height"], frame["width"] * 4)
        surface.set_device_scale(frame["width"] / width, frame["height"] / height)
        context.set_source_surface(surface, 0, 0)
        context.paint()

    area.set_draw_func(draw)
    window.set_child(area)

    def let_clicks_through(_window) -> None:
        window.get_surface().set_input_region(cairo.Region())
        _report_scale(window.get_surface().get_scale())

    window.connect("map", let_clicks_through)

    monitors = Gdk.Display.get_default().get_monitors()

    def report_largest_scale(*_args) -> None:
        scales = [monitors.get_item(index).get_scale() for index in range(monitors.get_n_items())]
        _report_scale(max(scales, default=1.0))

    monitors.connect("items-changed", report_largest_scale)
    report_largest_scale()

    loop = GLib.MainLoop()

    def show(width_px: int, height_px: int, visible: bool, pixels: bytearray) -> bool:
        frame.update(width=width_px, height=height_px, pixels=pixels)
        if visible:
            window.set_visible(True)
            area.queue_draw()
        else:
            window.set_visible(False)
        return GLib.SOURCE_REMOVE

    def read_frames() -> None:
        frames = sys.stdin.buffer
        while header := frames.read(FRAME_HEADER.size):
            if len(header) < FRAME_HEADER.size:
                break
            width_px, height_px, visible = FRAME_HEADER.unpack(header)
            pixels = bytearray(frames.read(width_px * height_px * 4))
            if len(pixels) < width_px * height_px * 4:
                break
            GLib.idle_add(show, width_px, height_px, bool(visible), pixels)
        GLib.idle_add(loop.quit)  # Ghostwriter closed the pipe

    threading.Thread(target=read_frames, name="Frames", daemon=True).start()
    loop.run()


_reported: list[float] = []


def _report_scale(scale: float) -> None:
    if _reported != [scale]:
        _reported[:] = [scale]
        _say(f"scale {scale}")


def _say(line: str) -> None:
    print(line, flush=True)


if __name__ == "__main__":
    main(*(int(argument) for argument in sys.argv[1:4]))
