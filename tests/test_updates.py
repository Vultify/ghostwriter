"""Check for updates: comparing versions, reading GitHub's answer, and every outcome of the tray menu item."""

import io
import json

import pytest

from ghostwriter import app, updates, win32


@pytest.mark.parametrize(("latest", "current", "newer"), [
    ("1.2.0", "1.1.0", True),
    ("1.10.0", "1.9.3", True),
    ("2.0.0", "1.99.99", True),
    ("1.1.0", "1.1.0", False),
    ("1.0.9", "1.1.0", False),
])
def test_versions_compare_by_number_not_by_text(latest, current, newer):
    assert updates.is_newer(latest, current) is newer


def test_the_latest_version_comes_from_the_github_release_tag(monkeypatch):
    reply = io.BytesIO(json.dumps({"tag_name": "v1.4.2"}).encode())
    monkeypatch.setattr(updates.urllib.request, "urlopen", lambda request, timeout: reply)
    assert updates.latest_version() == "1.4.2"


class FakeTray:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def notify(self, message: str) -> None:
        self.messages.append(message)


@pytest.fixture
def update_check(monkeypatch):
    """Run the tray's update check against a pretend GitHub and a pretend yes or no answer."""
    started = []
    monkeypatch.setattr(updates, "is_git_checkout", lambda: False)
    monkeypatch.setattr(updates, "start_update", lambda: started.append(True))
    monkeypatch.setattr(app, "__version__", "1.1.0")
    monkeypatch.setattr(updates, "__version__", "1.1.0")

    def run(latest, answer=win32.IDYES):
        if isinstance(latest, Exception):
            def fail():
                raise latest
            monkeypatch.setattr(updates, "latest_version", fail)
        else:
            monkeypatch.setattr(updates, "latest_version", lambda: latest)
        monkeypatch.setattr(app.user32, "MessageBoxW", lambda *args: answer)
        tray = FakeTray()
        app.check_for_updates(tray)
        return tray.messages, bool(started)

    return run


def test_up_to_date(update_check):
    assert update_check("1.1.0") == (["You're up to date (version 1.1.0)."], False)


def test_offline_or_unreachable(update_check):
    messages, started = update_check(OSError("no internet"))
    assert messages == ["Couldn't check for updates. Check your internet connection and try again."]
    assert not started


def test_a_newer_version_updates_only_when_you_say_yes(update_check):
    assert update_check("1.2.0", answer=win32.IDYES) == ([], True)


def test_saying_no_leaves_everything_alone(update_check):
    assert update_check("1.2.0", answer=7) == ([], False)


def test_a_git_checkout_is_never_overwritten(monkeypatch):
    monkeypatch.setattr(updates, "is_git_checkout", lambda: True)
    monkeypatch.setattr(updates, "latest_version", lambda: pytest.fail("should not go online"))
    tray = FakeTray()
    app.check_for_updates(tray)
    assert tray.messages == ["This copy of Ghostwriter is a git checkout, so update it with git pull instead."]
