"""Other apps' sound, as the Windows volume mixer lists it, so Ghostwriter can turn it down while it listens.

pycaw and comtypes load on the thread that uses them, since loading them sets that thread up for Windows' audio
objects, and the tray app and the app window keep their own threads untouched.
"""

import logging
import os
from _ctypes import COMError  # what comtypes raises; loading it here doesn't set up anything

log = logging.getLogger("ghostwriter")

_ACTIVE = 1  # AudioSessionStateActive: the app has sound going right now


class AppVolume:
    """One app's sound in the volume mixer, with its own volume from 0 to 1."""

    def __init__(self, volume, key: str, process: int) -> None:
        self._volume = volume
        self.key = key  # the same for this app every time it runs, so it can be found again after a restart
        self.process = process

    @property
    def level(self) -> float:
        """Raises OSError if the app has closed, like on every system."""
        try:
            return self._volume.GetMasterVolume()
        except COMError as error:
            raise OSError(f"Couldn't read an app's volume: {error}") from error

    @level.setter
    def level(self, value: float) -> None:
        try:
            self._volume.SetMasterVolume(max(0.0, min(1.0, value)), None)
        except COMError as error:
            raise OSError(f"Couldn't set an app's volume: {error}") from error


def prepare_thread() -> None:
    """Set up the calling thread for Windows' audio objects. Call it once on the thread that changes volumes."""
    import comtypes
    comtypes.CoInitialize()


def other_apps(playing_only: bool = True) -> list[AppVolume]:
    """Every app with sound on any speaker or headset, except Ghostwriter and Windows' system sounds. By default
    only the ones playing right now; the rest are paused or quiet but still in the volume mixer."""
    import comtypes
    from pycaw.pycaw import (DEVICE_STATE, AudioUtilities, EDataFlow, IAudioSessionControl2, IAudioSessionManager2,
                             ISimpleAudioVolume)

    apps = []
    devices = AudioUtilities.GetDeviceEnumerator().EnumAudioEndpoints(EDataFlow.eRender.value,
                                                                      DEVICE_STATE.ACTIVE.value)
    for device_index in range(devices.GetCount()):
        try:
            manager = devices.Item(device_index).Activate(IAudioSessionManager2._iid_, comtypes.CLSCTX_ALL, None)
            sessions = manager.QueryInterface(IAudioSessionManager2).GetSessionEnumerator()
            for session_index in range(sessions.GetCount()):
                session = sessions.GetSession(session_index).QueryInterface(IAudioSessionControl2)
                process = session.GetProcessId()
                if (playing_only and session.GetState() != _ACTIVE) or process in (0, os.getpid()):  # 0: system
                    continue
                apps.append(AppVolume(session.QueryInterface(ISimpleAudioVolume), session.GetSessionIdentifier(),
                                      process))
        except (COMError, OSError) as error:  # a headset unplugged mid search, or an app closing
            log.debug("Skipped a sound device: %s", error)
    return apps
