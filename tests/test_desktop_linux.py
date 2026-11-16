"""Linux's small services: one copy at a time, opening files, message boxes, the light or dark theme, and sounds."""

import os
import subprocess
import sys

import numpy as np
import pytest

from ghostwriter.linux import desktop
from ghostwriter.paths import PROJECT
from ghostwriter.sounds import STYLES, sound_path


def test_only_one_copy_holds_a_name_and_a_crash_frees_it():
    name = f"GhostwriterTest{os.getpid()}"
    holder = subprocess.Popen(
        [sys.executable, "-c", "import sys, time; from ghostwriter.linux import desktop; "
         f"print(desktop.claim_single_instance({name!r}), flush=True); time.sleep(30)"],
        cwd=PROJECT, stdout=subprocess.PIPE, text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "True"
        assert not desktop.claim_single_instance(name)
    finally:
        holder.kill()  # like a crash: no chance to let go of the name itself
        holder.wait()
    assert desktop.claim_single_instance(name)


def test_files_open_in_the_desktops_own_app(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(desktop.subprocess, "Popen", lambda args, **options: started.append((args, options)))
    desktop.open_path(tmp_path)
    args, options = started[0]
    assert args == ["xdg-open", str(tmp_path)]
    assert options["start_new_session"]  # it outlives Ghostwriter


@pytest.mark.parametrize("answer, said_yes", [(0, True), (1, False)])
def test_message_boxes_run_as_their_own_program(monkeypatch, answer, said_yes):
    asked = []

    def run(args, **options):
        asked.append(args)
        return subprocess.CompletedProcess(args, answer)

    monkeypatch.setattr(desktop.subprocess, "run", run)
    assert desktop.ask_yes_no("Update now?") is said_yes
    desktop.show_error("Something broke")
    assert asked == [[sys.executable, "-m", "ghostwriter.linux.dialog", "question", "Update now?"],
                     [sys.executable, "-m", "ghostwriter.linux.dialog", "error", "Something broke"]]


@pytest.mark.parametrize("scheme, theme", [(2, "light"), (1, "dark"), (0, "dark"), (None, "dark")])
def test_the_theme_follows_the_desktops_light_or_dark_setting(monkeypatch, scheme, theme):
    monkeypatch.setattr(desktop, "_color_scheme", lambda: scheme)
    assert desktop.apps_theme() == theme
    assert desktop.taskbar_is_light() is (theme == "light")


def test_the_desktop_answers_whether_it_is_light_or_dark():
    assert desktop._color_scheme() in (0, 1, 2, None)


@pytest.mark.parametrize("style", STYLES)
def test_every_sound_is_ready_to_play(style):
    for part in ("start", "stop"):
        samples, rate = desktop._read_wav(sound_path(style, part))
        assert samples.dtype == np.int16 and samples.ndim == 2 and len(samples) > 0
        assert rate > 0
