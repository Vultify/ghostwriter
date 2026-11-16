"""Stand-ins for the mic, the speech engine, and the paster, for tests that only need dictation's flow."""


class FakeRecorder:
    open_ms = 0.0

    def start(self) -> None:
        pass

    def stop(self):
        return [0.0]


class FakeTranscriber:
    def transcribe(self, audio, prompt=None) -> str:
        return "hello"


class FakePaster:
    def __init__(self) -> None:
        self.pasted: list[str] = []

    def paste(self, text: str) -> bool:
        self.pasted.append(text)
        return True
