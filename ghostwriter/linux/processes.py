"""Starting helper programs on Linux, tied to Ghostwriter so they close when it does."""

import ctypes
import functools
import os
import queue
import signal
import subprocess
import threading
from concurrent.futures import Future

NO_WINDOW = 0  # creationflags is Windows only; Linux programs never open a console of their own

_PR_SET_PDEATHSIG = 1
_libc = ctypes.CDLL(None, use_errno=True)


class Children:
    """Programs Ghostwriter starts that close when it does, even after a crash. Linux sends each one SIGTERM when the
    thread that started it ends, so they're all started from one thread that lives until close()."""

    def __init__(self) -> None:
        self._requests: queue.Queue[tuple | None] = queue.Queue()
        self._thread = threading.Thread(target=self._serve, name="Helper programs", daemon=True)
        self._thread.start()

    def start(self, args: list[str], **options) -> subprocess.Popen:
        started: Future[subprocess.Popen] = Future()
        self._requests.put((args, options, started))
        return started.result()

    def close(self) -> None:
        """Let go of the programs; any still running get SIGTERM."""
        self._requests.put(None)
        self._thread.join(timeout=5)

    def _serve(self) -> None:
        while (request := self._requests.get()) is not None:
            args, options, started = request
            try:
                started.set_result(subprocess.Popen(
                    args, preexec_fn=functools.partial(_close_with_parent, os.getpid()), **options))
            except Exception as error:
                started.set_exception(error)


def _close_with_parent(parent: int) -> None:
    """Runs in the new program just before it starts: ask Linux to end it along with the thread that started it."""
    _libc.prctl(_PR_SET_PDEATHSIG, signal.SIGTERM)
    if os.getppid() != parent:  # Ghostwriter ended before the line above took effect
        os._exit(1)
