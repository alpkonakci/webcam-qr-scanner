"""Windows-only smoke check against real, hidden OpenCV windows.

Run from the repository root: python -m tests.native_cursor_smoke
"""

import ctypes
import os

import cv2

from window_cursor import HTCLIENT, WM_SETCURSOR, _cursor_api, set_window_arrow


def main() -> None:
    if os.name != "nt":
        raise SystemExit("This smoke check requires Windows.")
    menu_title = f"QR Scanner cursor smoke {os.getpid()}"
    selection_title = f"QR Scanner selection smoke {os.getpid()}"
    user32, _, _, _ = _cursor_api()
    user32.ShowWindow.argtypes = (ctypes.c_void_p, ctypes.c_int)
    user32.FindWindowExW.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p)
    user32.FindWindowExW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.GetCursor.restype = ctypes.c_void_p
    try:
        for title in (menu_title, selection_title):
            cv2.namedWindow(title, cv2.WINDOW_AUTOSIZE)
            hwnd = user32.FindWindowW("Main HighGUI class", title)
            assert hwnd, "OpenCV parent window was not found"
            user32.ShowWindow(hwnd, 0)
        assert set_window_arrow(menu_title), "Cursor subclass could not be installed"
        for title, cursor_id in ((menu_title, 32512), (selection_title, 32515)):
            hwnd = user32.FindWindowW("Main HighGUI class", title)
            child = user32.FindWindowExW(hwnd, None, "HighGUI class", None)
            assert child, "OpenCV image window was not found"
            user32.SendMessageW(child, WM_SETCURSOR, child, HTCLIENT)
            assert user32.GetCursor() == user32.LoadCursorW(None, cursor_id), title
        cv2.destroyWindow(menu_title)
        cv2.namedWindow(menu_title, cv2.WINDOW_AUTOSIZE)
        user32.ShowWindow(user32.FindWindowW("Main HighGUI class", menu_title), 0)
        assert set_window_arrow(menu_title), "Reopened window could not be subclassed"
        print("Native cursor smoke PASS: image-area arrow, independent selection crosshair, reopen.")
    finally:
        for title in (menu_title, selection_title):
            try:
                cv2.destroyWindow(title)
            except cv2.error:
                pass
        cv2.waitKey(1)


if __name__ == "__main__":
    main()
