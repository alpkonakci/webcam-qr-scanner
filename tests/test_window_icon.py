from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from window_icon import _icon_handles, icon_path, set_window_icon


class WindowIconTests(unittest.TestCase):
    def setUp(self) -> None:
        _icon_handles.cache_clear()

    def tearDown(self) -> None:
        _icon_handles.cache_clear()

    def test_windows_icon_contains_taskbar_and_explorer_sizes(self) -> None:
        with Image.open(icon_path()) as image:
            self.assertEqual(image.format, "ICO")
            self.assertTrue(
                {(16, 16), (32, 32), (48, 48), (256, 256)}
                <= image.info["sizes"]
            )

    def test_packaged_icon_is_loaded_from_bundle(self) -> None:
        with patch("window_icon.sys._MEIPASS", "C:/bundle", create=True):
            self.assertEqual(
                icon_path(),
                Path("C:/bundle/assets/QR-Scanner.ico"),
            )

    def test_native_window_receives_large_and_small_icons(self) -> None:
        user32 = Mock()
        user32.LoadImageW.side_effect = (101, 102)
        user32.FindWindowW.return_value = 123
        with (
            patch("window_icon.os.name", "nt"),
            patch("window_icon.ctypes.windll.user32", user32),
        ):
            self.assertTrue(set_window_icon("QR Scanner"))

        self.assertEqual(user32.LoadImageW.call_count, 2)
        user32.SendMessageW.assert_any_call(123, 0x0080, 1, 101)
        user32.SendMessageW.assert_any_call(123, 0x0080, 0, 102)


if __name__ == "__main__":
    unittest.main()
