"""The program that shows the listening pill on Linux: a Wayland overlay layer (wlr-layer-shell, through
gtk4-layer-shell), the kind bars and notifications use. It never takes the keyboard, lets clicks through, and opens
on the screen in use each time it's shown. GNOME has no overlay layers, so it says so and quits there.

Ghostwriter starts it with the pill's size and bottom margin in logical pixels and sends it frames on stdin. A frame
is FRAME_HEADER (width and height in pixels, then 1 to show or 0 to hide) followed by width * height premultiplied
BGRA pixels. It answers on stdout, one line each: READY once it takes frames, "scale <number>" for the screen scale
to draw at, UNSUPPORTED on a desktop without overlay layers, or MISSING and what's missing."""

import ctypes
import struct
import sys
import threading

FRAME_HEADER = struct.Struct("<HHB")
NAMESPACE = "ghostwriter-pill"
LAYER_SHELL_LIBRARY = "libgtk4-layer-shell.so.0"
READY = "ready"
UNSUPPORTED = "unsupported"
MISSING = "missing"


def main(width: int, height: int, bottom_margin: int) -> None:
    try:
        # gtk4-layer-shell has to load before GTK does, so it can hook GTK's Wayland calls.
        ctypes.CDLL(LAYER_SHELL_LIBRARY)
        import cairo
        import gi

        gi.require_version("Gdk", "4.0")
        gi.require_version("Gtk", "4.0")
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gdk, GLib, Gtk
        from gi.repository import Gtk4LayerShell as LayerShell
    except (OSError, ImportError, ValueError) as error:
        _say(f"{MISSING} {error}")
        return
    wayland = Gtk.init_check() and Gdk.Display.get_default().__gtype__.name == "GdkWaylandDisplay"
    if not wayland or not LayerShell.is_supported():
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

    shown: dict = {}
    area = Gtk.DrawingArea(content_width=width, content_height=height)

    def draw(_area, context, _width, _height) -> None:
        if not shown:
            return
        surface = cairo.ImageSurface.create_for_data(shown["pixels"], cairo.FORMAT_ARGB32, shown["width"],
                                                     shown["height"], shown["width"] * 4)
        surface.set_device_scale(shown["width"] / width, shown["height"] / height)
        context.set_source_surface(surface, 0, 0)
        context.paint()

    area.set_draw_func(draw)
    window.set_child(area)

    def watch_scale(_window) -> None:
        surface = window.get_surface()
        surface.connect("notify::scale", lambda *_args: _report_scale(surface.get_scale()))

    def on_map(_window) -> None:
        surface = window.get_surface()
        surface.set_input_region(cairo.Region())  # clicks go through to the window underneath
        _report_scale(surface.get_scale())  # the screen it opened on

    window.connect("realize", watch_scale)
    window.connect("map", on_map)

    # A first guess until it opens on a screen: the largest scale, so the first frame is never blurry.
    monitors = Gdk.Display.get_default().get_monitors()
    _report_scale(max((monitors.get_item(index).get_scale() for index in range(monitors.get_n_items())),
                      default=1.0))

    loop = GLib.MainLoop()
    latest: list = []  # only the newest frame waits, so a stalled screen never builds up a backlog
    lock = threading.Lock()

    def show_latest() -> bool:
        with lock:
            width_px, height_px, visible, pixels = latest.pop()
        if visible:
            shown.update(width=width_px, height=height_px, pixels=pixels)
            window.set_visible(True)
            area.queue_draw()
        else:
            window.set_visible(False)
        return GLib.SOURCE_REMOVE

    def read_frames() -> None:
        frames = sys.stdin.buffer
        while len(header := frames.read(FRAME_HEADER.size)) == FRAME_HEADER.size:
            width_px, height_px, visible = FRAME_HEADER.unpack(header)
            pixels = bytearray(frames.read(width_px * height_px * 4))
            if len(pixels) < width_px * height_px * 4:
                break
            with lock:
                waiting = bool(latest)
                latest[:] = [(width_px, height_px, bool(visible), pixels)]
            if not waiting:
                GLib.idle_add(show_latest)
        GLib.idle_add(loop.quit)  # Ghostwriter closed the pipe

    threading.Thread(target=read_frames, name="Frames", daemon=True).start()
    _say(READY)
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
