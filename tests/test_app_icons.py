import sys
from pathlib import Path

import pytest

from ghostwriter import app_icons
from ghostwriter.system import paster

PNG = b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture(autouse=True)
def no_remembered_misses(monkeypatch):
    """Each test starts with no apps remembered as having no icon."""
    monkeypatch.setattr(app_icons, "_without_icon", {})


def test_an_apps_icon_is_saved_once_and_read_back_as_a_data_url(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(paster, "app_icon", lambda app: calls.append(app) or PNG)

    app_icons.remember("Notepad", Path("notepad.exe"), tmp_path)
    app_icons.remember("Notepad", Path("notepad.exe"), tmp_path)

    assert calls == [Path("notepad.exe")]
    urls = app_icons.data_urls(["Notepad", "Unknown app"], tmp_path)
    assert list(urls) == ["Notepad"]
    assert urls["Notepad"].startswith("data:image/png;base64,")


def test_ghostwriter_and_apps_without_an_icon_save_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(paster, "app_icon", lambda app: None)

    app_icons.remember("Ghostwriter", Path("python.exe"), tmp_path)
    app_icons.remember("Some game", Path("game.exe"), tmp_path)
    app_icons.remember("Unknown app", None, tmp_path)

    assert not tmp_path.exists() or not any(tmp_path.iterdir())


def test_an_app_without_an_icon_is_looked_up_again_only_after_a_while(tmp_path, monkeypatch):
    calls, now = [], [1000.0]
    monkeypatch.setattr(paster, "app_icon", lambda app: calls.append(app))
    monkeypatch.setattr(app_icons.time, "monotonic", lambda: now[0])
    for _ in range(3):
        app_icons.remember("Some game", Path("game.exe"), tmp_path)
    app_icons.remember("Some game", Path("other/game.exe"), tmp_path)  # another program with the same name
    assert calls == [Path("game.exe"), Path("other/game.exe")]
    now[0] += app_icons.RETRY_SECONDS
    app_icons.remember("Some game", Path("game.exe"), tmp_path)  # a failure can be temporary
    assert calls[-1] == Path("game.exe") and len(calls) == 3


def test_a_broken_icon_never_stops_the_dictation(tmp_path, monkeypatch):
    def broken(app):
        raise OSError("no access")

    monkeypatch.setattr(paster, "app_icon", broken)
    app_icons.remember("Locked app", Path("locked.exe"), tmp_path)  # doesn't raise
    assert app_icons.data_urls(["Locked app"], tmp_path) == {}


@pytest.mark.skipif(sys.platform != "win32", reason="reads a Windows program's icon")
def test_windows_reads_a_programs_icon_as_a_png():
    png = paster.app_icon(Path(r"C:\Windows\System32\notepad.exe"))
    assert png and png.startswith(b"\x89PNG")
    assert paster.app_icon(Path(r"C:\no such folder\nothing.exe")) is None


@pytest.mark.skipif(sys.platform != "win32", reason="reads a Windows program's icon")
def test_windows_icons_keep_soft_edges_and_their_black_parts():
    from io import BytesIO

    from PIL import Image

    notepad = Image.open(BytesIO(paster.app_icon(Path(r"C:\Windows\System32\notepad.exe")))).convert("RGBA")
    edges = [pixel for pixel in notepad.get_flattened_data() if 0 < pixel[3] < 255]
    assert edges and max(sum(pixel[:3]) for pixel in edges) > 150  # soft edges keep their color, not a dark halo
    console = Image.open(BytesIO(paster.app_icon(Path(r"C:\Windows\System32\cmd.exe")))).convert("RGBA")
    assert any(pixel == (0, 0, 0, 255) for pixel in console.get_flattened_data())  # the console's black stays solid
