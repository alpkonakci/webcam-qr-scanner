from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

from window_cursor import (
    HTCLIENT, SUBCLASS_ID, WM_NCDESTROY, WM_SETCURSOR,
    _cursor_api, set_window_arrow,
)


class WindowCursorTests(unittest.TestCase):
    def setUp(self) -> None:
        _cursor_api.cache_clear()
        self.user32 = Mock()
        self.kernel32 = Mock()
        self.comctl32 = Mock()
        self.user32.FindWindowW.return_value = 123
        self.user32.FindWindowExW.return_value = 124
        self.user32.LoadCursorW.return_value = 456
        self.kernel32.GetCurrentThreadId.return_value = 789
        self.comctl32.SetWindowSubclass.return_value = 1
        self.comctl32.DefSubclassProc.return_value = 42

        def window_thread(_hwnd, process_id):
            process_id._obj.value = os.getpid()
            return 789

        self.user32.GetWindowThreadProcessId.side_effect = window_thread
        self.patches = [
            patch("window_cursor.os.name", "nt"),
            patch("window_cursor.ctypes.windll.user32", self.user32),
            patch("window_cursor.ctypes.windll.kernel32", self.kernel32),
            patch("window_cursor.ctypes.windll.comctl32", self.comctl32),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        _cursor_api.cache_clear()
        for item in reversed(self.patches):
            item.stop()

    def test_client_uses_system_arrow_and_keeps_callback_alive(self) -> None:
        self.assertTrue(set_window_arrow("QR Scanner"))
        self.user32.FindWindowW.assert_called_once_with("Main HighGUI class", "QR Scanner")
        callback = _cursor_api()[3]
        self.comctl32.SetWindowSubclass.assert_any_call(123, callback, SUBCLASS_ID, 456)
        self.comctl32.SetWindowSubclass.assert_any_call(124, callback, SUBCLASS_ID, 456)
        self.assertEqual(self.comctl32.SetWindowSubclass.call_count, 2)
        self.assertEqual(callback(123, WM_SETCURSOR, 999, HTCLIENT, SUBCLASS_ID, 456), 1)
        self.user32.SetCursor.assert_called_once_with(456)
        self.comctl32.DefSubclassProc.assert_not_called()
        self.assertIs(callback, _cursor_api()[3])

    def test_resize_cursor_and_other_events_are_not_overridden(self) -> None:
        self.assertTrue(set_window_arrow("QR Scanner"))
        callback = _cursor_api()[3]
        self.assertEqual(callback(123, WM_SETCURSOR, 123, 10, SUBCLASS_ID, 456), 42)
        self.assertEqual(callback(123, 0x0200, 0, 0, SUBCLASS_ID, 456), 42)
        self.user32.SetCursor.assert_not_called()

    def test_destroy_removes_subclass_before_delegating(self) -> None:
        self.assertTrue(set_window_arrow("QR Scanner"))
        callback = _cursor_api()[3]
        self.assertEqual(callback(123, WM_NCDESTROY, 0, 0, SUBCLASS_ID, 456), 42)
        self.comctl32.RemoveWindowSubclass.assert_called_once_with(123, callback, SUBCLASS_ID)

    def test_other_thread_is_not_subclassed(self) -> None:
        self.kernel32.GetCurrentThreadId.return_value = 999
        self.assertFalse(set_window_arrow("QR Scanner"))
        self.comctl32.SetWindowSubclass.assert_not_called()

    def test_other_process_is_not_subclassed(self) -> None:
        def other_process(_hwnd, process_id):
            process_id._obj.value = os.getpid() + 1
            return 789
        self.user32.GetWindowThreadProcessId.side_effect = other_process
        self.assertFalse(set_window_arrow("QR Scanner"))
        self.comctl32.SetWindowSubclass.assert_not_called()

    def test_missing_window_or_cursor_is_safe(self) -> None:
        self.user32.FindWindowW.return_value = 0
        self.assertFalse(set_window_arrow("QR Scanner"))
        self.user32.FindWindowW.return_value = 123
        self.user32.LoadCursorW.return_value = 0
        self.assertFalse(set_window_arrow("QR Scanner"))
        self.comctl32.SetWindowSubclass.assert_not_called()

    def test_missing_image_window_is_safe(self) -> None:
        self.user32.FindWindowExW.return_value = 0
        self.assertFalse(set_window_arrow("QR Scanner"))
        self.comctl32.SetWindowSubclass.assert_not_called()

    def test_non_windows_is_noop(self) -> None:
        with patch("window_cursor.os.name", "posix"):
            self.assertFalse(set_window_arrow("QR Scanner"))
        self.user32.FindWindowW.assert_not_called()


if __name__ == "__main__":
    unittest.main()
