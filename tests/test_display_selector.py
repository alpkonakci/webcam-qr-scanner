from __future__ import annotations

import unittest

import numpy as np

from display_selector import (
    LIST_TOP,
    ROW_GAP,
    ROW_HEIGHT,
    WINDOW_WIDTH,
    build_display_selector_canvas,
    display_at_point,
    window_height,
)
from screen_capture import ConnectedDisplay, ScreenBounds


class DisplaySelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.displays = (
            ConnectedDisplay(
                1,
                "\\\\.\\DISPLAY1",
                ScreenBounds(0, 0, 1920, 1080),
                True,
            ),
            ConnectedDisplay(
                2,
                "\\\\.\\DISPLAY2",
                ScreenBounds(1920, 0, 2560, 1440),
                False,
            ),
        )

    def test_canvas_lists_connected_screens(self) -> None:
        canvas = build_display_selector_canvas(self.displays)

        self.assertEqual(
            canvas.shape,
            (window_height(len(self.displays)), WINDOW_WIDTH, 3),
        )
        self.assertEqual(canvas.dtype, np.uint8)

    def test_each_screen_row_is_an_explicit_click_target(self) -> None:
        first_y = LIST_TOP + ROW_HEIGHT // 2
        second_y = LIST_TOP + ROW_HEIGHT + ROW_GAP + ROW_HEIGHT // 2

        self.assertEqual(
            display_at_point(100, first_y, display_count=2, scroll_offset=0),
            0,
        )
        self.assertEqual(
            display_at_point(100, second_y, display_count=2, scroll_offset=0),
            1,
        )
        self.assertIsNone(
            display_at_point(10, first_y, display_count=2, scroll_offset=0)
        )


if __name__ == "__main__":
    unittest.main()
