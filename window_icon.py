"""Apply the bundled QR Scanner icon to native OpenCV windows on Windows."""

from __future__ import annotations

import ctypes
import os
import sys
from functools import lru_cache
from pathlib import Path


def icon_path() -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return bundle_root / "assets" / "QR-Scanner.ico"


@lru_cache(maxsize=1)
def _icon_handles() -> tuple[int, int]:
    path = icon_path()
    if not path.is_file():
        return (0, 0)
    try:
        load_image = ctypes.windll.user32.LoadImageW
        load_image.argtypes = (
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        )
        load_image.restype = ctypes.c_void_p
        large = int(load_image(None, str(path), 1, 32, 32, 0x0010) or 0)
        small = int(load_image(None, str(path), 1, 16, 16, 0x0010) or 0)
        # These two icon handles are reused by all windows in this process and
        # released by Windows when the short-lived GUI process exits.
        return (large, small)
    except (AttributeError, OSError, TypeError, ValueError):
        return (0, 0)


def set_window_icon(title: str) -> bool:
    """Best-effort title-bar and taskbar branding for one OpenCV window."""

    if os.name != "nt":
        return False
    large, small = _icon_handles()
    if not large and not small:
        return False
    try:
        user32 = ctypes.windll.user32
        find_window = user32.FindWindowW
        send_message = user32.SendMessageW
        find_window.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
        find_window.restype = ctypes.c_void_p
        send_message.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        )
        send_message.restype = ctypes.c_ssize_t
        window_handle = find_window(None, title)
        if not window_handle:
            return False
        if large:
            send_message(window_handle, 0x0080, 1, large)  # WM_SETICON, ICON_BIG
        if small:
            send_message(window_handle, 0x0080, 0, small)  # ICON_SMALL
        return True
    except (AttributeError, OSError, TypeError, ValueError):
        return False
