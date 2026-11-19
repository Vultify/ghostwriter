"""Ghostwriter as Omarchy's dictation app: the commands Omarchy runs, against a stand-in Ghostwriter, and the row in
Omarchy's menu. Everything happens in the test's own folders, with stand-ins for the commands that would reach the
real desktop or a real running Ghostwriter."""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

if sys.platform != "linux":  # skipped here rather than in conftest, so a Linux-only change stays out of shared files
    pytest.skip("Linux only", allow_module_level=True)

from ghostwriter.linux import omarchy_dictation  # noqa: E402

# A stand-in for the tray app: started as `python -m ghostwriter` like the real one, it writes down each dictation
# signal it gets.
STAND_IN = """
import signal, sys
numbers = {numbers}
signal.pthread_sigmask(signal.SIG_BLOCK, numbers)
open(sys.argv[1], "w").close()
while True:
    number = signal.sigwait(numbers)
    with open(sys.argv[1], "a") as heard:
        heard.write(signal.Signals(number).name + "\\n")
"""


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    """The commands installed in a folder of the test's own, with stand-ins for pgrep (so the real Ghostwriter is never
    found and signalled) and for uwsm-app and ghostwriter's launcher (which write down how they were started)."""
    commands = tmp_path / "bin"
    omarchy_dictation.add_commands(commands)
    (commands / "pgrep").write_text("#!/bin/sh\nexit 1\n")
    (commands / "uwsm-app").write_text('#!/bin/sh\n[ "$1" = -- ] && shift\nexec "$@"\n')
    (commands / "ghostwriter").write_text(f'#!/bin/sh\necho "$@" >> {tmp_path / "started"}\n')
    for name in ("pgrep", "uwsm-app", "ghostwriter"):
        (commands / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{commands}:{os.environ['PATH']}")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    (tmp_path / "state" / "ghostwriter").mkdir(parents=True)
    return tmp_path


def _dictate(command: str) -> subprocess.CompletedProcess:
    return subprocess.run(["omarchy-dictation-ghostwriter", command], capture_output=True, text=True, timeout=10)


def _status(folder: Path, **fields) -> None:
    (folder / "state" / "ghostwriter" / "status.json").write_text(json.dumps({"pid": 0, "state": "ready", **fields}))


def _wait_for(path: Path, lines: int) -> list[str]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        found = path.read_text().split() if path.exists() else []
        if len(found) >= lines:
            return found
        time.sleep(0.02)
    return found


@pytest.fixture
def stand_in(desktop):
    """A running stand-in Ghostwriter and the file it writes down its signals in."""
    package = desktop / "ghostwriter"
    package.mkdir()
    (package / "__init__.py").touch()
    (package / "__main__.py").write_text(
        STAND_IN.format(numbers=sorted(int(number) for number in omarchy_dictation.SIGNALS.values())))
    heard = desktop / "heard"
    process = subprocess.Popen([sys.executable, "-m", "ghostwriter", str(heard)], cwd=desktop)
    deadline = time.monotonic() + 5
    while not heard.exists() and time.monotonic() < deadline:  # its signals are blocked once the file exists
        time.sleep(0.02)
    yield process, heard
    process.kill()
    process.wait()


def test_each_command_reaches_the_running_ghostwriter_as_its_signal(desktop, stand_in):
    process, heard = stand_in
    _status(desktop, pid=process.pid)
    for command in ("start", "stop", "toggle"):
        assert _dictate(command).returncode == 0
        time.sleep(0.05)  # Omarchy runs them one at a time too
    assert _wait_for(heard, 3) == ["SIGUSR1", "SIGUSR2", "SIGRTMIN"]
    assert not (desktop / "started").exists()


def test_a_ghostwriter_still_loading_is_never_signalled(desktop, stand_in):
    # Started by a press moments ago, it hasn't written its status yet, and a signal would end it.
    _, heard = stand_in
    _status(desktop, pid=os.getpid(), state="stopped")
    (desktop / "state" / "ghostwriter" / "starting").touch()
    for command in ("stop", "toggle", "start"):
        assert _dictate(command).returncode == 0
    time.sleep(0.2)
    assert heard.read_text() == ""
    assert not (desktop / "started").exists()


def test_a_press_with_ghostwriter_not_running_starts_it_in_the_bar_once(desktop):
    _status(desktop, pid=os.getpid(), state="stopped")
    assert _dictate("stop").returncode == 0  # letting go never starts it
    assert not (desktop / "started").exists()
    assert _dictate("start").returncode == 0
    assert _wait_for(desktop / "started", 1) == ["--tray"]
    assert _dictate("toggle").returncode == 0  # still loading, so no second copy
    time.sleep(0.2)
    assert (desktop / "started").read_text().split() == ["--tray"]


def test_a_stale_status_file_naming_another_program_isnt_signalled(desktop):
    sleeper = subprocess.Popen(["sleep", "30"])
    try:
        _status(desktop, pid=sleeper.pid)
        assert _dictate("start").returncode == 0
        assert _wait_for(desktop / "started", 1) == ["--tray"]
        assert sleeper.poll() is None  # a stop signal would have ended it
    finally:
        sleeper.kill()
        sleeper.wait()


def test_the_adapter_refuses_unknown_commands(desktop):
    result = _dictate("record")
    assert result.returncode == 1 and "Usage" in result.stderr


def test_the_launcher_command_starts_this_copy(tmp_path):
    omarchy_dictation.add_commands(tmp_path)
    text = (tmp_path / "ghostwriter").read_text()
    assert f"cd -- {omarchy_dictation.PROJECT}" in text and '-m ghostwriter "$@"' in text
    assert os.access(tmp_path / "ghostwriter", os.X_OK)
    assert subprocess.run(["bash", "-n", tmp_path / "omarchy-install-dictation-ghostwriter"]).returncode == 0


def test_commands_by_the_same_name_that_ghostwriter_didnt_make_are_left_alone(tmp_path):
    (tmp_path / "ghostwriter").write_text("#!/bin/sh\necho someone else's\n")
    added = omarchy_dictation.add_commands(tmp_path)
    assert (tmp_path / "ghostwriter").read_text() == "#!/bin/sh\necho someone else's\n"
    assert {path.name for path in added} == {"omarchy-dictation-ghostwriter", "omarchy-install-dictation-ghostwriter"}
    assert len(omarchy_dictation.add_commands(tmp_path)) == 2  # its own are rewritten, so updates reach them


def _menu_rows(text: str) -> dict:
    """Read an Omarchy menu file the way its JSONC reader does: comments and trailing commas allowed."""
    text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    return json.loads(re.sub(r",(\s*})", r"\1", text))


def test_the_menu_row_joins_the_users_own_menu_file_once(tmp_path):
    menu = tmp_path / "omarchy-menu.jsonc"
    menu.write_text('{\n  // My own rows\n  "personal": {"icon":"","label":"Personal"},\n}\n')
    assert omarchy_dictation.add_menu_row(menu)
    assert not omarchy_dictation.add_menu_row(menu)
    rows = _menu_rows(menu.read_text())
    assert rows["personal"] == {"icon": "", "label": "Personal"}
    row = rows[omarchy_dictation.MENU_ROW]
    assert row["label"] == "Ghostwriter" and row["action"] == "omarchy-default-dictation ghostwriter"
    assert "// My own rows" in menu.read_text()


def test_the_menu_row_makes_the_menu_file_when_there_isnt_one(tmp_path):
    menu = tmp_path / "extensions" / "omarchy-menu.jsonc"
    assert omarchy_dictation.add_menu_row(menu)
    assert list(_menu_rows(menu.read_text())) == [omarchy_dictation.MENU_ROW]


def test_omarchys_keys_are_reported_for_the_window_and_panel():
    assert omarchy_dictation.keys(uses_altgr=False)["hold"] == "Right Alt"
    assert omarchy_dictation.keys(uses_altgr=True) == {
        "desktop": "Omarchy", "hold": None, "toggle": "Alt + Space", "change": "Setup > Defaults > Dictation"}
