"""Starting up on a new PC: the GPU check, the one time model download and its progress, and passing that progress
to the app window."""

import json

from ghostwriter import startup, transcriber
from ghostwriter.app import _download_reporter
from ghostwriter.transcriber import gpu_available, model_downloaded, model_path


def test_this_pc_has_a_gpu_whisper_can_use():
    assert gpu_available()


def test_this_pc_already_has_the_speech_model():
    assert model_downloaded()


def _fake_hub(monkeypatch, downloaded: bool) -> list[bool]:
    """Stands in for huggingface_hub, reporting progress the way it does: bytes received, plus a bar counting files."""
    calls = []

    def snapshot_download(repo, allow_patterns, local_files_only=False, tqdm_class=None):
        calls.append(local_files_only)
        if local_files_only and not downloaded:
            raise FileNotFoundError("not downloaded yet")
        if tqdm_class:
            received = tqdm_class(total=0, name="huggingface_hub.snapshot_download.transfer", disable=True)
            received.total = 300  # the total grows as each file starts
            files = tqdm_class(total=5, name="huggingface_hub.snapshot_download", disable=True)
            for _ in range(3):
                received.update(100)
            files.update(5)
        return "models/turbo"

    monkeypatch.setattr(transcriber, "snapshot_download", snapshot_download)
    return calls


def test_the_first_run_downloads_and_reports_the_bytes_received(monkeypatch):
    calls = _fake_hub(monkeypatch, downloaded=False)
    progress = []
    assert model_path(on_progress=lambda done, total: progress.append((done, total))) == "models/turbo"
    assert calls == [True, False]  # looked on disk first
    assert progress == [(100, 300), (200, 300), (300, 300)]


def test_an_already_downloaded_model_starts_offline(monkeypatch):
    calls = _fake_hub(monkeypatch, downloaded=True)
    progress = []
    assert model_path(on_progress=lambda done, total: progress.append(done)) == "models/turbo"
    assert calls == [True]
    assert progress == []


def test_the_window_reads_what_the_tray_app_writes(tmp_path):
    path = tmp_path / "startup.json"
    assert startup.read(path) == {}
    startup.write(path, model="downloading", done=5, total=10)
    assert startup.read(path) == {"model": "downloading", "done": 5, "total": 10}
    path.write_text('{"model": "downl', encoding="utf-8")  # caught halfway through a write
    assert startup.read(path) == {}


def test_download_progress_is_saved_a_few_times_a_second_and_always_at_the_end(tmp_path):
    path = tmp_path / "startup.json"
    report = _download_reporter(path, every=60)
    report(1, 10)
    report(2, 10)  # too soon after the last one
    assert json.loads(path.read_text(encoding="utf-8"))["done"] == 1
    report(10, 10)
    assert json.loads(path.read_text(encoding="utf-8"))["done"] == 10
