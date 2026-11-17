"""Picking a mic on Linux: the mics come from PipeWire under the names the desktop's sound settings show, and a
recording opens on the picked one."""

import json
import os
import shutil
import subprocess
import sys
import time

import pytest

if sys.platform != "linux":  # skipped here rather than in conftest, like the other Linux-only files
    pytest.skip("Linux only", allow_module_level=True)

import numpy as np  # noqa: E402

from ghostwriter.linux import microphones  # noqa: E402
from ghostwriter.paths import PROJECT  # noqa: E402
from ghostwriter.recorder import Recorder, list_microphones  # noqa: E402


def _node(node_id, media_class, name, description=None):
    properties = {"media.class": media_class, "node.name": name}
    if description:
        properties["node.description"] = description
    return {"id": node_id, "type": "PipeWire:Interface:Node", "info": {"props": properties}}


def test_mics_are_listed_by_the_names_the_sound_settings_show(monkeypatch):
    dump = [
        _node(40, "Audio/Sink", "alsa_output.speakers", "Speakers"),
        _node(41, "Audio/Source", "alsa_input.usb-rode", "RODECaster Duo"),
        _node(42, "Audio/Source", "alsa_input.usb-blue-1", "Yeti"),
        _node(43, "Audio/Source", "alsa_input.usb-blue-2", "Yeti"),
        _node(44, "Audio/Source/Virtual", "noise_suppressed_mic", "Noise Suppressed Mic"),
        _node(45, "Stream/Input/Audio", "firefox-capture", "Firefox"),
        _node(46, "Video/Source", "v4l2_input.camera", "Camera"),
        _node(47, "Audio/Source", "alsa_input.no-description"),
        {"id": 3, "type": "PipeWire:Interface:Link", "info": {"props": {"media.class": "Audio/Source"}}},
    ]
    monkeypatch.setattr(microphones.subprocess, "run",
                        lambda *args, **options: subprocess.CompletedProcess(args, 0, json.dumps(dump)))
    assert microphones.microphones() == {
        "RODECaster Duo": "alsa_input.usb-rode",
        "Yeti": "alsa_input.usb-blue-1",
        "Yeti (2)": "alsa_input.usb-blue-2",
        "Noise Suppressed Mic": "noise_suppressed_mic",
        "alsa_input.no-description": "alsa_input.no-description",
    }


def test_without_pipewire_only_the_system_default_is_offered(monkeypatch):
    def missing(*args, **options):
        raise FileNotFoundError("pw-dump")

    monkeypatch.setattr(microphones.subprocess, "run", missing)
    assert microphones.microphones() == {}


def test_a_recording_names_its_mic_only_while_it_opens(monkeypatch, caplog):
    monkeypatch.setattr(microphones, "_nodes", {"Yeti": "alsa_input.usb-blue"})
    monkeypatch.setattr(microphones, "microphones", lambda: {})
    default = os.environ["PIPEWIRE_NODE"]
    with microphones.recording_from("Yeti") as device:
        assert device is None and os.environ["PIPEWIRE_NODE"] == "alsa_input.usb-blue"
    assert os.environ["PIPEWIRE_NODE"] == default  # programs Ghostwriter starts later get the default
    with microphones.recording_from(None):
        assert os.environ["PIPEWIRE_NODE"] == default
    with microphones.recording_from("Unplugged mic"):
        assert os.environ["PIPEWIRE_NODE"] == default
    assert "Mic 'Unplugged mic' isn't connected" in caplog.text


PIPEWIRE_TOOLS = ("pw-loopback", "pw-dump", "pw-link")


@pytest.fixture
def virtual_mic():
    """A temporary mic that plays back whatever goes into its sink, gone when the test ends. Low priority, so it
    never becomes the default."""
    if not all(shutil.which(tool) for tool in PIPEWIRE_TOOLS) or not microphones.microphones():
        pytest.skip("needs PipeWire with a mic")
    sink, mic, label = f"ghostwriter_test_in_{os.getpid()}", f"ghostwriter_test_mic_{os.getpid()}", "Ghostwriter Test Mic"
    loopback = subprocess.Popen(
        ["pw-loopback", f"--capture-props=media.class=Audio/Sink node.name={sink} priority.session=0",
         f"--playback-props=media.class=Audio/Source node.name={mic} node.description=\"{label}\" priority.session=0"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if label in microphones.microphones():
                break
            time.sleep(0.05)
        else:
            pytest.fail("the test mic never showed up")
        yield label, sink, mic
    finally:
        loopback.terminate()
        loopback.wait()


def _tone_into(sink, seconds):
    """Play a tone into a sink, from its own program so the PipeWire target only applies there."""
    return subprocess.Popen(
        [sys.executable, "-c",
         "import numpy as np, sounddevice as sd, sys\n"
         "rate = 48000; t = np.arange(int(rate * float(sys.argv[1]))) / rate\n"
         "sd.play((0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), rate, blocking=True)",
         str(seconds)],
        cwd=PROJECT, env={**os.environ, "PIPEWIRE_NODE": sink})


def _linked_to(node):
    links = subprocess.run(["pw-link", "-l"], capture_output=True, text=True).stdout
    return any(line.strip().startswith(f"|<- {node}:") for line in links.splitlines())


def test_a_recording_hears_the_picked_mic(virtual_mic):
    label, sink, mic = virtual_mic
    assert label in list_microphones()
    tone = _tone_into(sink, 2)
    try:
        time.sleep(0.3)
        recorder = Recorder(microphone=label)
        recorder.start()
        time.sleep(0.6)
        assert _linked_to(mic)
        heard = recorder.stop()
    finally:
        tone.wait()
    assert float(np.sqrt(np.mean(heard * heard))) > 0.1  # the tone, not a quiet room

    recorder = Recorder(microphone=None)
    recorder.start()
    time.sleep(0.3)
    try:
        assert not _linked_to(mic)  # back on the system default
    finally:
        recorder.stop()
