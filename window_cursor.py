"""Use the system arrow in OpenCV menus without changing selection cursors."""

from __future__ import annotations

import ctypes
import os
from functools import lru_cache

WM_SETCURSOR = 0x0020
WM_NCDESTROY = 0x0082
HTCLIENT = 1
SUBCLASS_ID = 0x57515253


@lru_cache(maxsize=1)
def _cursor_api():
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    comctl32 = ctypes.windll.comctl32
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint,
        ctypes.c_size_t, ctypes.c_ssize_t, ctypes.c_size_t, ctypes.c_size_t,
    )
    user32.FindWindowW.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.FindWindowExW.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p)
    user32.FindWindowExW.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
    user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    kernel32.GetCurrentThreadId.restype = ctypes.c_ulong
    user32.LoadCursorW.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    user32.LoadCursorW.restype = ctypes.c_void_p
    user32.SetCursor.argtypes = (ctypes.c_void_p,)
    user32.SetCursor.restype = ctypes.c_void_p
    comctl32.SetWindowSubclass.argtypes = (ctypes.c_void_p, callback_type, ctypes.c_size_t, ctypes.c_size_t)
    comctl32.SetWindowSubclass.restype = ctypes.c_int
    comctl32.RemoveWindowSubclass.argtypes = (ctypes.c_void_p, callback_type, ctypes.c_size_t)
    comctl32.RemoveWindowSubclass.restype = ctypes.c_int
    comctl32.DefSubclassProc.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
    comctl32.DefSubclassProc.restype = ctypes.c_ssize_t

    @callback_type
    def callback(hwnd, message, wparam, lparam, subclass_id, cursor):
        if message == WM_SETCURSOR and (lparam & 0xFFFF) == HTCLIENT:
            user32.SetCursor(cursor)
            return 1
        if message == WM_NCDESTROY:
            comctl32.RemoveWindowSubclass(hwnd, callback, subclass_id)
        # Leave borders, resize handles, title bars and all other events native.
        return comctl32.DefSubclassProc(hwnd, message, wparam, lparam)

    # Windows does not retain Python callback references. Keep this singleton
    # alive for the process lifetime, including windows destroyed and reopened.
    return user32, kernel32, comctl32, callback


def set_window_arrow(title: str) -> bool:
    """Best-effort, UI-thread-only cursor override for this process's window.

    Both parent and image windows are scoped individually. No shared window
    class or system-wide cursor is changed; area selectors are untouched.
    """
    if os.name != "nt":
        return False
    try:
        user32, kernel32, comctl32, callback = _cursor_api()
        hwnd = user32.FindWindowW("Main HighGUI class", title)
        if not hwnd:
            return False
        image_hwnd = user32.FindWindowExW(hwnd, None, "HighGUI class", None)
        if not image_hwnd:
            return False
        for handle in (hwnd, image_hwnd):
            process_id = ctypes.c_ulong()
            thread_id = user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
            if process_id.value != os.getpid() or thread_id != kernel32.GetCurrentThreadId():
                return False
        cursor = user32.LoadCursorW(None, 32512)  # IDC_ARROW; shared, not destroyed.
        if not cursor:
            return False
        parent_set = comctl32.SetWindowSubclass(hwnd, callback, SUBCLASS_ID, cursor)
        image_set = comctl32.SetWindowSubclass(image_hwnd, callback, SUBCLASS_ID, cursor)
        return bool(parent_set and image_set)
    except (AttributeError, OSError, TypeError, ValueError):
        return False
