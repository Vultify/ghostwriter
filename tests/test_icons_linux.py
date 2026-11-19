"""App icons on Linux, for History: the icon an app's launcher entry names, found in the icon theme the way
launchers find it. Uses a stand-in theme and launcher entries."""

import io
import sys
from pathlib import Path

import pytest

if sys.platform != "linux":  # skipped here rather than in conftest, so a Linux-only change stays out of shared files
    pytest.skip("Linux only", allow_module_level=True)

from PIL import Image  # noqa: E402

from ghostwriter.linux import desktop_files, icon_theme  # noqa: E402
from ghostwriter.linux.paster import App, app_icon  # noqa: E402

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
       '<rect width="16" height="16" fill="#ff0000"/></svg>')


def _png(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (*color, 255)).save(path)


@pytest.fixture(autouse=True)
def icon_themes(tmp_path, monkeypatch):
    shared, home = tmp_path / "shared", tmp_path / "home"
    (shared / "icons" / "Plain").mkdir(parents=True)
    (shared / "icons" / "Plain" / "index.theme").write_text(
        "[Icon Theme]\nName=Plain\nInherits=hicolor\nDirectories=48x48/apps,scalable/apps\n\n"
        "[48x48/apps]\nSize=48\nType=Fixed\n\n[scalable/apps]\nSize=48\nMinSize=8\nMaxSize=512\nType=Scalable\n")
    (shared / "icons" / "hicolor").mkdir()
    (shared / "icons" / "hicolor" / "index.theme").write_text(
        "[Icon Theme]\nName=Hicolor\nDirectories=16x16/apps,48x48/apps,256x256/apps\n\n"
        "[16x16/apps]\nSize=16\nType=Threshold\n\n[48x48/apps]\nSize=48\nType=Threshold\n\n"
        "[256x256/apps]\nSize=256\nType=Threshold\n")
    _png(shared / "icons" / "hicolor" / "16x16" / "apps" / "gw-editor.png", (16, 16), (0, 0, 255))
    _png(shared / "icons" / "hicolor" / "256x256" / "apps" / "gw-editor.png", (256, 256), (0, 255, 0))
    _png(shared / "icons" / "Plain" / "48x48" / "apps" / "gw-terminal.png", (48, 48), (255, 255, 0))
    _png(shared / "icons" / "hicolor" / "48x48" / "apps" / "gw-terminal.png", (48, 48), (0, 0, 0))
    (shared / "icons" / "Plain" / "scalable" / "apps").mkdir(parents=True)
    (shared / "icons" / "Plain" / "scalable" / "apps" / "gw-drawing.svg").write_text(SVG)
    _png(home / "icons" / "hicolor" / "256x256" / "apps" / "gw-video.png", (256, 256), (255, 0, 0))  # no index here
    _png(shared / "pixmaps" / "gw-oldapp.png", (32, 32), (255, 0, 255))
    _png(tmp_path / "gw-wide.png", (96, 48), (0, 255, 255))
    _png(shared / "icons" / "hicolor" / "48x48" / "apps" / "steam_icon_99999901.png", (48, 48), (128, 128, 128))

    entries = {
        "shared/applications/gw-editor.desktop": "[Desktop Entry]\nName=Editor\nIcon=gw-editor\n",
        "shared/applications/gw-terminal.desktop": "[Desktop Entry]\nName=Terminal\nIcon=gw-terminal.png\n",
        "shared/applications/gw-drawing.desktop": "[Desktop Entry]\nName=Drawing\nIcon=gw-drawing\n",
        "shared/applications/gw-oldapp.desktop": "[Desktop Entry]\nName=Old app\nIcon=gw-oldapp\n",
        "shared/applications/gw-wide.desktop": f"[Desktop Entry]\nName=Wide\nIcon={tmp_path / 'gw-wide.png'}\n",
        "home/applications/YouTube.desktop":
            "[Desktop Entry]\nName=YouTube\nExec=omarchy-launch-webapp https://gw-video.example/\nIcon=gw-video\n",
    }
    for relative, text in entries.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(home))
    # The system's folder stays last: GdkPixbuf tells file types apart with the MIME database kept there.
    monkeypatch.setenv("XDG_DATA_DIRS", f"{shared}:/usr/share")
    monkeypatch.setattr(icon_theme, "current_theme", lambda: "Plain")
    desktop_files.installed.cache_clear()
    icon_theme.clear_cache()
    yield
    desktop_files.installed.cache_clear()
    icon_theme.clear_cache()


def _icon(app_id: str) -> Image.Image | None:
    png = app_icon(App(None, app_id, ""))
    return Image.open(io.BytesIO(png)).convert("RGBA") if png else None


def test_an_apps_icon_comes_from_its_launcher_entry_at_48_pixels():
    icon = _icon("gw-editor")
    assert icon.size == (48, 48)
    assert icon.getpixel((24, 24))[:3] == (0, 255, 0)  # the big version shrunk, not the blurry small one grown


def test_the_current_theme_wins_over_the_ones_it_inherits():
    assert _icon("gw-terminal").getpixel((24, 24))[:3] == (255, 255, 0)  # also when the entry names a file extension


def test_scalable_icons_are_drawn_at_the_size_wanted():
    icon = _icon("gw-drawing")
    assert icon.size == (48, 48) and icon.getpixel((24, 24))[:3] == (255, 0, 0)


def test_web_apps_steam_games_and_old_pixmaps_get_their_icons():
    assert _icon("chrome-gw-video.example__-Default").getpixel((24, 24))[:3] == (255, 0, 0)  # from the user's own folder
    assert _icon("steam_app_99999901").getpixel((24, 24))[:3] == (128, 128, 128)
    assert _icon("gw-oldapp").getpixel((24, 24))[:3] == (255, 0, 255)


def test_a_wide_icon_is_centered_on_a_clear_square():
    icon = _icon("gw-wide")
    assert icon.size == (48, 48)
    assert icon.getpixel((24, 24))[3] == 255 and icon.getpixel((24, 2))[3] == 0


def test_an_app_without_an_icon_gets_none():
    assert _icon("mystery-app") is None
    assert app_icon(None) is None
