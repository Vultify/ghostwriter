"""The tray ghost on Linux. It talks to the bar directly over D-Bus with the two protocols Linux bars read
(StatusNotifierItem for the icon, dbusmenu for its menu), so a left click opens the menu and the ghost is sent as
pixels, with no GTK window and no temporary files. ghostwriter.tray builds the menu the same way on every system."""

import logging

import numpy as np
from gi.repository import Gio, GLib
from PIL import Image
from pystray import Menu, MenuItem
from pystray._base import Icon as BaseIcon

ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
WATCHER = "org.kde.StatusNotifierWatcher"
NOTIFICATIONS = "org.freedesktop.Notifications"
ICON_SIZES = (16, 22, 24, 32, 48, 64)
ROOT = 0

_INTERFACES = Gio.DBusNodeInfo.new_for_xml("""
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus"><arg type="s"/></signal>
  </interface>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
      <arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/>
      <arg type="u" direction="in"/>
    </method>
    <method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
    <method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
    <method name="AboutToShowGroup">
      <arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/>
    </method>
    <signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
    <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
    <signal name="ItemActivationRequested"><arg type="i"/><arg type="u"/></signal>
  </interface>
</node>
""")
_ITEM, _MENU = _INTERFACES.interfaces

log = logging.getLogger("ghostwriter")


class _Entry:
    """One row of the menu as the bar sees it: its properties, the rows under it, and what clicking it does."""

    def __init__(self, props: dict[str, GLib.Variant], item: MenuItem | None = None) -> None:
        self.props = props
        self.item = item
        self.children: list[int] = []


class Icon(BaseIcon):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._bus: Gio.DBusConnection | None = None
        self._loop: GLib.MainLoop | None = None
        self._status = "Passive"
        self._pixmaps = _pixmaps(None)
        self._entries: dict[int, _Entry] = {ROOT: _Entry({})}
        self._revision = 0
        self._notification = 0

    def _run(self) -> None:
        # Its own main loop on this thread, so D-Bus calls from the bar are answered here and nowhere else.
        context = GLib.MainContext.new()
        context.push_thread_default()
        self._loop = GLib.MainLoop.new(context, False)
        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        objects = [
            self._bus.register_object(ITEM_PATH, _ITEM, self._on_item_call, self._item_property, None),
            self._bus.register_object(MENU_PATH, _MENU, self._on_menu_call, self._menu_property, None),
        ]
        # Registers again whenever the bar (re)starts.
        watch = Gio.bus_watch_name_on_connection(self._bus, WATCHER, Gio.BusNameWatcherFlags.NONE,
                                                 lambda *_: self._register(), None)
        self._mark_ready()
        try:
            self._loop.run()
        finally:
            Gio.bus_unwatch_name(watch)
            for registration in objects:
                self._bus.unregister_object(registration)
            context.pop_thread_default()

    def _run_detached(self) -> None:
        raise NotImplementedError("The Linux tray runs on its own thread")

    def _stop(self) -> None:
        self._loop.quit()

    def _show(self) -> None:
        self._status = "Active"
        self._emit(ITEM_PATH, _ITEM.name, "NewStatus", GLib.Variant("(s)", (self._status,)))
        self._register()

    def _hide(self) -> None:
        self._status = "Passive"
        self._emit(ITEM_PATH, _ITEM.name, "NewStatus", GLib.Variant("(s)", (self._status,)))

    def _update_icon(self) -> None:
        self._pixmaps = _pixmaps(self.icon)
        self._icon_valid = True
        self._emit(ITEM_PATH, _ITEM.name, "NewIcon")

    def _update_title(self) -> None:
        self._emit(ITEM_PATH, _ITEM.name, "NewTitle")
        self._emit(ITEM_PATH, _ITEM.name, "NewToolTip")

    def _update_menu(self) -> None:
        entries = {ROOT: _Entry({"children-display": GLib.Variant("s", "submenu")})}
        if self.menu:
            _add_rows(entries, ROOT, self.menu)
        self._entries = entries
        self._revision += 1
        self._emit(MENU_PATH, _MENU.name, "LayoutUpdated", GLib.Variant("(ui)", (self._revision, ROOT)))

    def _notify(self, message: str, title: str | None = None) -> None:
        self._notification = Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            NOTIFICATIONS, "/org/freedesktop/Notifications", NOTIFICATIONS, "Notify",
            GLib.Variant("(susssasa{sv}i)", (self.name, self._notification, "", title or self.title, message, [], {},
                                              -1)),
            GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]

    def _remove_notification(self) -> None:
        if self._notification:
            Gio.bus_get_sync(Gio.BusType.SESSION, None).call(
                NOTIFICATIONS, "/org/freedesktop/Notifications", NOTIFICATIONS, "CloseNotification",
                GLib.Variant("(u)", (self._notification,)), None, Gio.DBusCallFlags.NONE, -1, None, None)
            self._notification = 0

    def _register(self) -> None:
        """Tell the bar the ghost is here."""
        if self._bus is None or self._status != "Active":
            return
        self._bus.call(WATCHER, "/StatusNotifierWatcher", WATCHER, "RegisterStatusNotifierItem",
                       GLib.Variant("(s)", (ITEM_PATH,)), None, Gio.DBusCallFlags.NONE, -1, None, None)

    def _emit(self, path: str, interface: str, signal: str, parameters: GLib.Variant | None = None) -> None:
        if self._bus is not None:
            self._bus.emit_signal(None, path, interface, signal, parameters)

    def _run_default(self) -> None:
        default = next((item for item in self.menu.items if item.default), None) if self.menu else None
        if default is not None:
            self._click(default)

    def _click(self, item: MenuItem) -> None:
        try:
            item(self)
        except Exception:
            log.exception("A tray menu action failed")
        self.update_menu()

    def _item_property(self, _bus, _sender, _path, _interface, name: str) -> GLib.Variant:
        values = {
            "Category": lambda: GLib.Variant("s", "ApplicationStatus"),
            "Id": lambda: GLib.Variant("s", self.name),
            "Title": lambda: GLib.Variant("s", self.title),
            "Status": lambda: GLib.Variant("s", self._status),
            "WindowId": lambda: GLib.Variant("i", 0),
            "IconName": lambda: GLib.Variant("s", ""),
            "IconPixmap": lambda: self._pixmaps,
            "ToolTip": lambda: GLib.Variant("(sa(iiay)ss)", ("", [], self.title, "")),
            "ItemIsMenu": lambda: GLib.Variant("b", True),  # a left click opens the menu
            "Menu": lambda: GLib.Variant("o", MENU_PATH),
        }
        return values[name]()

    def _on_item_call(self, _bus, _sender, _path, _interface, method: str, _parameters, invocation) -> None:
        # Bars that ask the app instead of opening the menu themselves (middle click, or a left click on some
        # desktops) run the menu's default row, like a left click on Windows.
        if method in ("Activate", "SecondaryActivate"):
            self._run_default()
        invocation.return_value(None)

    def _menu_property(self, _bus, _sender, _path, _interface, name: str) -> GLib.Variant:
        values = {
            "Version": GLib.Variant("u", 3),
            "TextDirection": GLib.Variant("s", "ltr"),
            "Status": GLib.Variant("s", "normal"),
            "IconThemePath": GLib.Variant("as", []),
        }
        return values[name]

    def _on_menu_call(self, _bus, _sender, _path, _interface, method: str, parameters: GLib.Variant,
                      invocation) -> None:
        entries = self._entries
        arguments = parameters.unpack()
        if method == "GetLayout":
            parent, depth, _names = arguments
            if parent not in entries:
                invocation.return_dbus_error("com.canonical.dbusmenu.Error.UnknownId", f"No row {parent}")
                return
            reply = GLib.Variant("(u(ia{sv}av))", (self._revision, _layout(entries, parent, depth)))
        elif method == "GetGroupProperties":
            ids, _names = arguments
            reply = GLib.Variant("(a(ia{sv}))", ([(row, entries[row].props) for row in ids if row in entries],))
        elif method == "GetProperty":
            row, name = arguments
            prop = entries[row].props.get(name) if row in entries else None
            if prop is None:
                invocation.return_dbus_error("com.canonical.dbusmenu.Error.UnknownProperty", f"No {name}")
                return
            reply = GLib.Variant("(v)", (prop,))
        elif method == "Event":
            self._event(entries, *arguments[:2])
            reply = None
        elif method == "EventGroup":
            missing = [row for row, event, *_ in arguments[0] if not self._event(entries, row, event)]
            reply = GLib.Variant("(ai)", (missing,))
        elif method == "AboutToShow":
            reply = GLib.Variant("(b)", (False,))
        else:  # AboutToShowGroup
            reply = GLib.Variant("(aiai)", ([], []))
        invocation.return_value(reply)

    def _event(self, entries: dict[int, _Entry], row: int, event: str) -> bool:
        """Handle a click on a row. False if there's no such row."""
        entry = entries.get(row)
        if entry is None:
            return False
        if event == "clicked" and entry.item is not None:
            self._click(entry.item)
        return True


def _add_rows(entries: dict[int, _Entry], parent: int, menu: Menu) -> None:
    """Number each row in order, so a menu that keeps its shape keeps its ids between updates."""
    for item in menu.items:
        row = len(entries)
        entries[parent].children.append(row)
        if item is Menu.SEPARATOR:
            entries[row] = _Entry({"type": GLib.Variant("s", "separator")})
            continue
        props = {
            "label": GLib.Variant("s", item.text.replace("_", "__")),  # a lone _ underlines the next letter
            "enabled": GLib.Variant("b", item.enabled),
        }
        if item.submenu:
            props["children-display"] = GLib.Variant("s", "submenu")
        elif item.checked is not None:
            props["toggle-type"] = GLib.Variant("s", "radio" if item.radio else "checkmark")
            props["toggle-state"] = GLib.Variant("i", 1 if item.checked else 0)
        entries[row] = _Entry(props, None if item.submenu else item)
        if item.submenu:
            _add_rows(entries, row, item.submenu)


def _layout(entries: dict[int, _Entry], row: int, depth: int) -> tuple:
    """A row and the rows under it, depth levels down (-1 for all of them), in dbusmenu's nested shape."""
    entry = entries[row]
    children = [] if depth == 0 else [
        GLib.Variant("(ia{sv}av)", _layout(entries, child, depth - 1)) for child in entry.children
    ]
    return row, entry.props, children


def _pixmaps(image: Image.Image | None) -> GLib.Variant:
    """The icon at a few sizes as ARGB pixels, the format bars draw, so each bar picks the size it needs. The pixels
    go in as one block per size: handing GLib a list of numbers takes it seconds."""
    pixmaps = []
    for size in ICON_SIZES if image else ():
        rgba = np.asarray(image.convert("RGBA").resize((size, size), Image.LANCZOS))
        pixels = GLib.Variant.new_from_bytes(GLib.VariantType("ay"), GLib.Bytes.new(rgba[..., [3, 0, 1, 2]].tobytes()),
                                             True)
        pixmaps.append(GLib.Variant.new_tuple(GLib.Variant("i", size), GLib.Variant("i", size), pixels))
    return GLib.Variant.new_array(GLib.VariantType("(iiay)"), pixmaps)
