"""Manage the current user's optional Windows startup entry."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Webcam QR Scanner Bridge"


def startup_command() -> str:
    """Return the exact per-user command used after Windows sign-in."""

    if bool(getattr(sys, "frozen", False)):
        command = [sys.executable, "--bridge"]
    else:
        python_windowed = Path(sys.executable).with_name("pythonw.exe")
        executable = (
            python_windowed
            if python_windowed.exists()
            else Path(sys.executable)
        )
        command = [
            str(executable),
            str(Path(__file__).with_name("launcher.py")),
            "--bridge",
        ]
    return subprocess.list2cmdline(command)


def is_startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return False
    return value == startup_command()


def set_startup_enabled(enabled: bool) -> None:
    """Create or remove only this application's current-user startup value."""

    if sys.platform != "win32":
        raise OSError("Windows startup registration is only available on Windows")
    import winreg

    if enabled:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(
                key,
                VALUE_NAME,
                0,
                winreg.REG_SZ,
                startup_command(),
            )
        return

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass
