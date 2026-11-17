"""Picking a mic on Linux: the mics come from the sound server under the names the desktop's sound settings show,
and a recording opens on the picked one."""

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


def _source(name, description=None, device_class="sound"):
    source = {"name": name, "properties": {"device.class": device_class}}
    if description:
        source["description"] = description
    return source


def test_mics_are_listed_by_the_names_the_sound_settings_show(monkeypatch):
    sources = [
        _source("alsa_output.speakers.monitor", "Monitor of Speakers", "monitor"),
        _source("alsa_input.usb-rode", "RODECaster Duo"),
        _source("alsa_input.usb-blue-1", "Yeti"),
        _source("alsa_input.usb-blue-2", "Yeti"),
        _source("noise_suppressed_mic", "Noise Suppressed Mic", None),
        _source("alsa_input.no-description"),
        {"description": "Half made, no name yet"},
    ]
    monkeypatch.setattr(microphones.subprocess, "run",
                        lambda *args, **options: subprocess.CompletedProcess(args, 0, json.dumps(sources)))
    assert microphones.microphones() == {
        "RODECaster Duo": "alsa_input.usb-rode",
        "Yeti": "alsa_input.usb-blue-1",
        "Yeti (2)": "alsa_input.usb-blue-2",
        "Noise Suppressed Mic": "noise_suppressed_mic",
        "alsa_input.no-description": "alsa_input.no-description",
    }


def test_without_a_sound_server_only_the_system_default_is_offered(monkeypatch):
    def missing(*args, **options):
        raise FileNotFoundError("pactl")

    monkeypatch.setattr(microphones.subprocess, "run", missing)
    assert microphones.microphones() == {}


def test_a_mic_thats_gone_records_from_the_default_and_says_so(monkeypatch, caplog):
    opened = []
    monkeypatch.setattr(microphones, "microphones", lambda: {"Yeti": "alsa_input.usb-blue"})
    monkeypatch.setattr(microphones, "PulseStream", lambda source, rate, callback: opened.append(source))
    microphones.open_stream("Yeti", 16000, None)
    microphones.open_stream(None, 16000, None)
    microphones.open_stream("Unplugged mic", 16000, None)
    assert opened == ["alsa_input.usb-blue", None, None]
    assert "Mic 'Unplugged mic' isn't connected" in caplog.text


def test_without_pulseaudios_library_it_records_from_the_default_through_sounddevice(monkeypatch):
    def no_library(*args):
        raise OSError("libpulse-simple.so.0: cannot open shared object file")

    monkeypatch.setattr(microphones, "PulseStream", no_library)
    monkeypatch.setattr(microphones.sd, "InputStream", lambda **options: options)
    options = microphones.open_stream(None, 16000, print)
    assert options["samplerate"] == 16000 and options["channels"] == 1 and options["callback"] is print


PIPEWIRE_TOOLS = ("pw-loopback", "pactl", "pw-link")


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

    default = subprocess.run(["pactl", "get-default-source"], capture_output=True, text=True).stdout.strip()
    recorder = Recorder(microphone=None)
    recorder.start()
    time.sleep(0.3)
    try:
        assert _linked_to(default) and not _linked_to(mic)  # back on the system default
    finally:
        recorder.stop()
