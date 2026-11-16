"""Lowering other apps' sound while Ghostwriter listens: down to a share of each app's own volume, back up after,
hands off any app whose volume was changed by hand, and put back after Ghostwriter stops in the middle."""

import json
import subprocess
import sys
import threading
import time
import wave
from datetime import date, timedelta

import pytest

from ghostwriter.other_sounds import PENDING_DAYS, OtherSounds

LEVEL = 0.1  # the default, 10%


class FakeApp:
    def __init__(self, key: str, level: float, playing: bool = True) -> None:
        self.key = key
        self._level = level
        self.playing = playing  # a paused app is still in the volume mixer, just not playing
        self.closed = False

    @property
    def level(self) -> float:
        if self.closed:
            raise OSError("closed")
        return self._level

    @level.setter
    def level(self, value: float) -> None:
        if self.closed:
            raise OSError("closed")
        self._level = value


def _other_sounds(tmp_path, apps) -> OtherSounds:
    def found(playing_only: bool = True) -> list[FakeApp]:
        return [app for app in apps if app.playing or not playing_only]

    return OtherSounds(tmp_path / "lowered-sounds.json", apps=found, prepare_thread=lambda: None)


def test_other_apps_drop_to_10_percent_of_their_own_volume_and_come_back(tmp_path):
    apps = [FakeApp("music", 0.8), FakeApp("video", 1.0), FakeApp("muted", 0.0)]
    sounds = _other_sounds(tmp_path, apps)
    sounds.lower(LEVEL)
    sounds.lower(LEVEL)  # the second press of a double tap doesn't lower them further
    sounds.wait()
    assert [app.level for app in apps] == pytest.approx([0.8 * LEVEL, LEVEL, 0.0])
    assert sounds.path.exists()  # kept until they're back, in case Ghostwriter stops
    sounds.restore()
    sounds.wait()
    assert [app.level for app in apps] == pytest.approx([0.8, 1.0, 0.0])
    assert not sounds.path.exists()
    sounds.close()


def test_a_volume_changed_by_hand_or_a_closed_app_is_left_alone(tmp_path):
    music, video = FakeApp("music", 0.8), FakeApp("video", 1.0)
    sounds = _other_sounds(tmp_path, [music, video])
    sounds.lower(LEVEL)
    sounds.wait()
    music.level = 0.5  # turned down in the volume mixer while dictating
    video.closed = True
    sounds.restore()
    sounds.wait()
    assert music.level == 0.5
    sounds.close()


def test_closing_puts_them_back(tmp_path):
    music = FakeApp("music", 0.6)
    sounds = _other_sounds(tmp_path, [music])
    sounds.lower(LEVEL)
    sounds.close()
    assert music.level == pytest.approx(0.6)


def test_volumes_left_down_by_a_crash_go_back_on_the_next_start(tmp_path):
    (tmp_path / "lowered-sounds.json").write_text(json.dumps({"music": [0.8, 0.24], "game": [1.0, 0.3]}),
                                                  encoding="utf-8")
    music, game, chat = FakeApp("music", 0.24, playing=False), FakeApp("game", 0.7), FakeApp("chat", 0.24)
    sounds = _other_sounds(tmp_path, [music, game, chat])
    sounds.restore()  # does nothing itself, but waits behind the startup check
    sounds.wait()
    assert music.level == 0.8  # paused, but still put back
    assert game.level == 0.7  # changed by hand since, so it stays
    assert chat.level == 0.24  # never lowered by Ghostwriter
    assert not sounds.path.exists()
    sounds.close()


def test_an_app_closed_during_a_crash_is_put_back_once_it_opens_again(tmp_path):
    (tmp_path / "lowered-sounds.json").write_text(json.dumps({"game": [1.0, 0.1, date.today().isoformat()]}),
                                                  encoding="utf-8")
    apps = [FakeApp("music", 0.8)]
    sounds = _other_sounds(tmp_path, apps)
    sounds.lower(LEVEL)
    sounds.restore()
    sounds.wait()
    assert json.loads(sounds.path.read_text(encoding="utf-8")).keys() == {"game"}  # still waiting for the game
    apps.append(FakeApp("game", 0.1, playing=False))  # opened later, with the volume Windows remembered
    sounds.lower(LEVEL)
    sounds.restore()
    sounds.wait()
    assert [app.level for app in apps] == pytest.approx([0.8, 1.0])
    assert not sounds.path.exists()
    sounds.close()


def test_a_volume_waiting_too_long_is_given_up_on(tmp_path):
    old = (date.today() - timedelta(days=PENDING_DAYS + 1)).isoformat()
    (tmp_path / "lowered-sounds.json").write_text(json.dumps({"game": [1.0, 0.1, old]}), encoding="utf-8")
    sounds = _other_sounds(tmp_path, [])
    sounds.restore()
    sounds.wait()
    assert not sounds.path.exists()
    sounds.close()


SILENT_PLAYER = ("import os, sys, time, winsound; print(os.getpid(), flush=True); "
                 "winsound.PlaySound(sys.argv[1], winsound.SND_FILENAME | winsound.SND_LOOP | winsound.SND_ASYNC); "
                 "time.sleep(30)")


@pytest.mark.skipif(sys.platform != "win32", reason="checks the Windows volume mixer")
def test_a_real_app_in_the_windows_volume_mixer_goes_down_and_back(tmp_path):
    from ghostwriter.windows import volume

    silence = tmp_path / "silence.wav"
    with wave.open(str(silence), "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(44100)
        clip.writeframes(bytes(2 * 44100))
    player = subprocess.Popen([sys.executable, "-c", SILENT_PLAYER, str(silence)], stdout=subprocess.PIPE, text=True)
    try:
        process = int(player.stdout.readline())  # the venv's python.exe starts the real one as a child
        before = _levels(volume, process, wait=5)
        assert before, "the silent player never showed up in the volume mixer"
        sounds = OtherSounds(tmp_path / "lowered-sounds.json",
                             apps=lambda playing_only=True: [app for app in volume.other_apps(playing_only)
                                                             if app.process == process])
        sounds.lower(LEVEL)
        sounds.wait()
        lowered = _levels(volume, process)
        sounds.close()
        after = _levels(volume, process)
    finally:
        player.kill()
        player.wait()
    assert lowered == pytest.approx([level * LEVEL for level in before], abs=0.01)
    assert after == pytest.approx(before, abs=0.01)


def _levels(volume, process: int, wait: float = 0.0) -> list[float]:
    """The volume of each of a program's sounds, read on a thread set up for Windows' audio objects."""
    found = []

    def look() -> None:
        volume.prepare_thread()
        deadline = time.perf_counter() + wait
        while True:
            found[:] = [app.level for app in volume.other_apps() if app.process == process]
            if found or time.perf_counter() >= deadline:
                return
            time.sleep(0.1)

    thread = threading.Thread(target=look)
    thread.start()
    thread.join()
    return found
