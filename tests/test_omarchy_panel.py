"""Ghostwriter's panel for Omarchy's bar: Omarchy accepts the plugin, and every text it shows has an English string."""

import json
import re
import shutil
import subprocess

import pytest

from ghostwriter.paths import PROJECT

PLUGIN = PROJECT / "ghostwriter" / "linux" / "omarchy"


@pytest.mark.skipif(shutil.which("omarchy") is None, reason="needs Omarchy")
def test_omarchy_accepts_the_plugin():
    result = subprocess.run(["omarchy", "plugin", "validate", str(PLUGIN)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_string_the_panel_shows_is_written():
    panel = (PLUGIN / "Panel.qml").read_text(encoding="utf-8")
    english = json.loads((PLUGIN / "i18n" / "en.json").read_text(encoding="utf-8"))
    used = set(re.findall(r'strings\.t\("([^"]+)"\)', panel))
    assert used and used <= set(english), sorted(used - set(english))
    assert set(english) <= used, sorted(set(english) - used)  # no leftovers


def test_the_panel_never_reads_text_as_markup():
    """Omarchy's rule for plugins: text from files is shown as plain text, so it can't load anything."""
    panel = (PLUGIN / "Panel.qml").read_text(encoding="utf-8")
    assert panel.count("Text {") == panel.count("textFormat: Text.PlainText")
