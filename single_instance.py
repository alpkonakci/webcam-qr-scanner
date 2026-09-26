"""Windows named-mutex guard for the background tray process."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


ERROR_ALREADY_EXISTS = 183
BRIDGE_MUTEX_NAME = r"Local\WebcamQrScannerBridge"


class BridgeInstanceGuard:
    """Own the Windows-session bridge mutex for the lifetime of this object."""

    def __init__(self) -> None:
        self._handle: int | None = None
        self.already_running = False
        if sys.platform != "win32":
            return

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, False, BRIDGE_MUTEX_NAME)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self._handle = int(handle)
        self.already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS

    def close(self) -> None:
        if self._handle is None or sys.platform != "win32":
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle(self._handle)
        self._handle = None

    def __enter__(self) -> BridgeInstanceGuard:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
