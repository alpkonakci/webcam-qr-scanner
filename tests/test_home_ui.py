from __future__ import annotations

import unittest
from unittest.mock import patch

import cv2
import numpy as np

from home_ui import (
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    HomeAction,
    _bring_home_window_to_front,
    action_at_point,
    build_home_canvas,
    show_home_window,
)


class HomeUiTests(unittest.TestCase):
    def test_each_visible_action_has_an_explicit_click_target(self) -> None:
        self.assertIs(action_at_point(100, 150), HomeAction.SCAN_CAMERA)
        self.assertIs(action_at_point(100, 250), HomeAction.SCAN_SCREEN)
        self.assertIs(action_at_point(100, 350), HomeAction.PAIR_PHONE)
        self.assertIs(action_at_point(500, 490), HomeAction.EXIT)
        self.assertIsNone(action_at_point(20, 20))

    def test_canvas_has_stable_size_and_visible_content(self) -> None:
        canvas = build_home_canvas(hover_action=HomeAction.SCAN_SCREEN)

        self.assertEqual(canvas.shape, (WINDOW_HEIGHT, WINDOW_WIDTH, 3))
        self.assertEqual(canvas.dtype, np.uint8)
        self.assertGreater(int(canvas.max()), int(canvas.min()))

    def test_control_center_is_brought_forward_after_first_frame(self) -> None:
        with (
            patch("home_ui.cv2.namedWindow"),
            patch("home_ui.cv2.setMouseCallback"),
            patch("home_ui.cv2.moveWindow"),
            patch("home_ui.cv2.imshow"),
            patch("home_ui.cv2.waitKey", return_value=27),
            patch("home_ui.cv2.destroyWindow"),
            patch("home_ui._bring_home_window_to_front") as bring_forward,
        ):
            result = show_home_window()

        self.assertIs(result, HomeAction.BACKGROUND)
        bring_forward.assert_called_once_with()

    def test_foreground_helper_requests_an_always_visible_window(self) -> None:
        with (
            patch("home_ui.cv2.setWindowProperty") as set_property,
            patch("home_ui.os.name", "posix"),
        ):
            _bring_home_window_to_front()

        set_property.assert_called_once_with(
            "QR Scanner",
            cv2.WND_PROP_TOPMOST,
            1,
        )


if __name__ == "__main__":
    unittest.main()
