"""Linux's small services: one copy at a time, opening files, message boxes, the light or dark theme, and sounds."""

import os
import signal
import subprocess
import sys
import time
import wave

import numpy as np
import pytest
import sounddevice as sd

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


@pytest.mark.parametrize("quit_signal", [signal.SIGINT, signal.SIGTERM])
def test_ghostwriter_quits_cleanly_even_when_started_with_ctrl_c_ignored(quit_signal):
    """Like a copy started from Omarchy's panel, whose launcher ignores Ctrl+C."""
    program = subprocess.Popen(
        [sys.executable, "-c", "import time; from ghostwriter.linux import desktop; desktop.prepare()\n"
         "try:\n    print('ready', flush=True)\n    time.sleep(30)\n"
         "except KeyboardInterrupt:\n    print('stopped cleanly', flush=True)"],
        cwd=PROJECT, stdout=subprocess.PIPE, text=True,
        preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN),
    )
    try:
        assert program.stdout.readline().strip() == "ready"
        program.send_signal(quit_signal)
        assert program.stdout.readline().strip() == "stopped cleanly"
        assert program.wait(timeout=5) == 0
    finally:
        program.kill()
        program.wait()


def _needs_a_speaker():
    try:
        sd.query_devices(kind="output")
    except (sd.PortAudioError, ValueError):
        pytest.skip("no sound output on this machine")


def _silent_wav(folder):
    silence = folder / "silence.wav"
    with wave.open(str(silence), "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(44100)
        sound.writeframes(bytes(2 * 4410))  # a tenth of a second
    return silence


def test_a_sound_lets_go_of_the_speaker_when_it_ends(tmp_path):
    _needs_a_speaker()
    desktop.play_sound(_silent_wav(tmp_path), wait=True)
    playback = desktop._playing
    for _ in range(100):
        if playback.stream.closed:
            break
        time.sleep(0.02)
    assert playback.stream.closed


def test_sounds_started_from_many_threads_at_once_never_crash(tmp_path):
    """Quick clicks through the sound previews once crashed the app window: two threads stopped and started sounds
    at the same moment. Played through the real speaker, as silence."""
    _needs_a_speaker()
    silence = _silent_wav(tmp_path)
    program = subprocess.run(
        [sys.executable, "-c",
         "import sys, threading; from pathlib import Path; from ghostwriter.linux import desktop\n"
         "def clicks(wait):\n"
         "    for _ in range(15):\n"
         "        desktop.play_sound(Path(sys.argv[1]), wait=wait)\n"
         "threads = [threading.Thread(target=clicks, args=(n % 2 == 0,)) for n in range(8)]\n"
         "[thread.start() for thread in threads]\n[thread.join() for thread in threads]\nprint('done')",
         str(silence)],
        cwd=PROJECT, capture_output=True, text=True, timeout=60,
    )
    assert program.returncode == 0 and program.stdout.strip() == "done", program.stderr[-2000:]
