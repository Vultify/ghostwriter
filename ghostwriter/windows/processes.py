"""Starting helper programs on Windows with no console window, tied to Ghostwriter so they close when it does."""

import ctypes
import logging
import subprocess
from pathlib import Path

from ghostwriter.windows import win32
from ghostwriter.windows.win32 import kernel32

NO_WINDOW = subprocess.CREATE_NO_WINDOW  # creationflags for a program that shouldn't flash a console
NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE  # creationflags for a program that should get its own console

log = logging.getLogger("ghostwriter")


class Children:
    """Programs Ghostwriter starts that close when it does, even after a crash. A Windows job does the closing once
    Ghostwriter lets go of it."""

    def __init__(self) -> None:
        self._job = kernel32.CreateJobObjectW(None, None)
        limits = win32.JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = win32.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._job or not kernel32.SetInformationJobObject(self._job, win32.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                                                 ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())

    def start(self, args: list[str], **options) -> subprocess.Popen:
        program = subprocess.Popen(args, creationflags=NO_WINDOW, **options)
        self._add(program.pid, Path(args[0]).stem)
        return program

    def close(self) -> None:
        kernel32.CloseHandle(self._job)

    def _add(self, process_id: int, name: str) -> None:
        process = kernel32.OpenProcess(win32.PROCESS_SET_QUOTA | win32.PROCESS_TERMINATE, False, process_id)
        try:
            if not process or not kernel32.AssignProcessToJobObject(self._job, process):
                log.warning("Couldn't tie %s to Ghostwriter (error %d)", name, ctypes.get_last_error())
        finally:
            if process:
                kernel32.CloseHandle(process)
