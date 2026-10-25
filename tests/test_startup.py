"""Starting up on a new PC: the GPU check, and a heads-up before the one time model download."""

from ghostwriter import transcriber
from ghostwriter.transcriber import gpu_available, model_path


def test_this_pc_has_a_gpu_whisper_can_use():
    assert gpu_available()


def _fake_download(monkeypatch, downloaded: bool) -> list[bool]:
    calls = []

    def download_model(name, local_files_only=False):
        calls.append(local_files_only)
        if local_files_only and not downloaded:
            raise FileNotFoundError("not downloaded yet")
        return f"models/{name}"

    monkeypatch.setattr(transcriber, "download_model", download_model)
    return calls


def test_the_first_run_announces_the_download_before_starting_it(monkeypatch):
    calls = _fake_download(monkeypatch, downloaded=False)
    announced = []
    path = model_path("large-v3-turbo", on_download=lambda: announced.append(list(calls)))
    assert path == "models/large-v3-turbo"
    assert announced == [[True]]  # announced after the local check, before the real download
    assert calls == [True, False]


def test_an_already_downloaded_model_starts_quietly_and_offline(monkeypatch):
    calls = _fake_download(monkeypatch, downloaded=True)
    announced = []
    assert model_path("large-v3-turbo", on_download=lambda: announced.append(True)) == "models/large-v3-turbo"
    assert announced == []
    assert calls == [True]
