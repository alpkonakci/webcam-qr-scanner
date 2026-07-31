from __future__ import annotations

import unittest

import numpy as np

from home_ui import (
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    HomeAction,
    action_at_point,
    build_home_canvas,
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


if __name__ == "__main__":
    unittest.main()
