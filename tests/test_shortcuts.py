"""Start with Windows: a shortcut in the Startup folder that starts Ghostwriter in the tray when you log in."""

import subprocess

from ghostwriter.paths import PROJECT
from ghostwriter.windows import shortcuts


def _read_shortcut(path) -> list[str]:
    script = (f"$link = (New-Object -ComObject WScript.Shell).CreateShortcut('{path}'); "
              "$link.TargetPath; $link.Arguments; $link.WorkingDirectory")
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, check=True)
    return result.stdout.splitlines()


def test_start_with_windows_adds_and_removes_a_tray_only_shortcut(tmp_path):
    folder = tmp_path / "Startup"
    assert not shortcuts.starts_at_login(folder)
    shortcuts.set_start_at_login(True, folder)
    assert shortcuts.starts_at_login(folder)
    target, arguments, working_folder = _read_shortcut(folder / shortcuts.SHORTCUT_NAME)
    assert target.lower() == str(shortcuts.PYTHONW).lower()
    assert arguments == "-m ghostwriter --tray"
    assert working_folder.lower() == str(PROJECT).lower()
    shortcuts.set_start_at_login(False, folder)
    shortcuts.set_start_at_login(False, folder)  # turning it off twice is fine
    assert not shortcuts.starts_at_login(folder)


def test_the_real_startup_folder_is_the_one_windows_uses():
    assert shortcuts.startup_folder().parts[-4:] == ("Windows", "Start Menu", "Programs", "Startup")
