"""Launch modes of the same source tree or packaged executable safely."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Sequence


LAUNCHER_PATH = Path(__file__).with_name("launcher.py")
CREATE_NO_WINDOW = 0x08000000


def application_command(arguments: Sequence[str]) -> list[str]:
    """Build a shell-free command for source and PyInstaller execution."""

    if bool(getattr(sys, "frozen", False)):
        return [sys.executable, *arguments]
    return [sys.executable, str(LAUNCHER_PATH), *arguments]


def spawn_application(arguments: Sequence[str]) -> subprocess.Popen[bytes]:
    """Start an independent mode without opening a console window."""

    creation_flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.Popen(
        application_command(arguments),
        close_fds=True,
        creationflags=creation_flags,
    )

