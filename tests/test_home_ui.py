from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from home_ui import (
    BASE_ACTION_CARDS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    HomeAction,
    WindowCloseChoice,
    _bring_home_window_to_front,
    _disable_home_maximize,
    _home_window_closed,
    action_at_point,
    build_home_canvas,
    show_home_window,
)


class HomeUiTests(unittest.TestCase):
    def test_screen_action_explains_region_selection(self) -> None:
        screen_card = next(
            card
            for card in BASE_ACTION_CARDS
            if card.action is HomeAction.SCAN_SCREEN
        )

        self.assertEqual(screen_card.title, "Select a Screen Area")
        self.assertIn("drag around the QR code", screen_card.description)

    def test_each_visible_action_has_an_explicit_click_target(self) -> None:
        self.assertIs(action_at_point(100, 150), HomeAction.SCAN_CAMERA)
        self.assertIs(action_at_point(100, 250), HomeAction.SCAN_SCREEN)
        self.assertIs(action_at_point(100, 350), HomeAction.PAIR_PHONE)
        self.assertIs(action_at_point(500, 490), HomeAction.EXIT)
        self.assertIsNone(action_at_point(20, 20))

    def test_phone_card_switches_to_management_when_pairs_exist(self) -> None:
        self.assertIs(
            action_at_point(100, 350, pair_count=2),
            HomeAction.MANAGE_PHONES,
        )
        canvas = build_home_canvas(pair_count=2)

        self.assertEqual(canvas.shape, (WINDOW_HEIGHT, WINDOW_WIDTH, 3))

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

    def test_foreground_helper_does_not_leave_window_always_on_top(self) -> None:
        with (
            patch("home_ui.cv2.setWindowProperty") as set_property,
            patch("home_ui.os.name", "posix"),
        ):
            _bring_home_window_to_front()

        self.assertEqual(
            set_property.call_args_list,
            [
                unittest.mock.call("QR Scanner", cv2.WND_PROP_TOPMOST, 1),
                unittest.mock.call("QR Scanner", cv2.WND_PROP_TOPMOST, 0),
            ],
        )

    def test_maximize_is_disabled_for_fixed_size_control_center(self) -> None:
        user32 = Mock()
        user32.FindWindowW.return_value = 123
        user32.GetWindowLongPtrW.return_value = 0x00010000 | 0x00040000 | 0x10000000
        with (
            patch("home_ui.os.name", "nt"),
            patch("home_ui.ctypes.windll.user32", user32),
        ):
            _disable_home_maximize()

        user32.SetWindowLongPtrW.assert_called_once_with(123, -16, 0x10000000)
        user32.SetWindowPos.assert_called_once()

    def test_closed_window_property_error_still_opens_close_choice(self) -> None:
        with patch("home_ui.cv2.getWindowProperty", side_effect=cv2.error):
            self.assertTrue(_home_window_closed())

    def test_titlebar_close_can_hide_to_tray(self) -> None:
        with (
            patch("home_ui.cv2.namedWindow"),
            patch("home_ui.cv2.setMouseCallback"),
            patch("home_ui.cv2.moveWindow"),
            patch("home_ui.cv2.imshow"),
            patch("home_ui.cv2.waitKey", return_value=-1),
            patch("home_ui.cv2.getWindowProperty", return_value=-1),
            patch("home_ui.cv2.destroyWindow"),
            patch("home_ui._bring_home_window_to_front"),
        ):
            choose_close = Mock(return_value=WindowCloseChoice.BACKGROUND)
            result = show_home_window(choose_close=choose_close)

        self.assertIs(result, HomeAction.BACKGROUND)
        choose_close.assert_called_once_with()

    def test_titlebar_close_can_exit_without_second_confirmation(self) -> None:
        with (
            patch("home_ui.cv2.namedWindow"),
            patch("home_ui.cv2.setMouseCallback"),
            patch("home_ui.cv2.moveWindow"),
            patch("home_ui.cv2.imshow"),
            patch("home_ui.cv2.waitKey", return_value=-1),
            patch("home_ui.cv2.getWindowProperty", return_value=-1),
            patch("home_ui.cv2.destroyWindow"),
            patch("home_ui._bring_home_window_to_front"),
        ):
            confirm_exit = Mock()
            result = show_home_window(
                choose_close=lambda: WindowCloseChoice.EXIT,
                confirm_exit=confirm_exit,
            )

        self.assertIs(result, HomeAction.EXIT)
        confirm_exit.assert_not_called()

    def test_cancelling_titlebar_close_reopens_home(self) -> None:
        with (
            patch("home_ui.cv2.namedWindow") as named_window,
            patch("home_ui.cv2.setMouseCallback"),
            patch("home_ui.cv2.moveWindow"),
            patch("home_ui.cv2.imshow"),
            patch("home_ui.cv2.waitKey", side_effect=[-1, 27]),
            patch("home_ui.cv2.getWindowProperty", return_value=-1),
            patch("home_ui.cv2.destroyWindow"),
            patch("home_ui._bring_home_window_to_front") as bring_forward,
        ):
            result = show_home_window(
                choose_close=lambda: WindowCloseChoice.CANCEL,
            )

        self.assertIs(result, HomeAction.BACKGROUND)
        self.assertEqual(named_window.call_count, 2)
        self.assertEqual(bring_forward.call_count, 2)

    def test_cancelled_exit_keeps_control_center_open(self) -> None:
        mouse_callback = None

        def remember_callback(_: str, callback) -> None:
            nonlocal mouse_callback
            mouse_callback = callback

        wait_count = 0

        def click_exit_then_escape(_: int) -> int:
            nonlocal wait_count
            wait_count += 1
            if wait_count == 1 and mouse_callback is not None:
                mouse_callback(cv2.EVENT_LBUTTONUP, 500, 490, 0, None)
                return -1
            return 27

        with (
            patch("home_ui.cv2.namedWindow"),
            patch("home_ui.cv2.setMouseCallback", side_effect=remember_callback),
            patch("home_ui.cv2.moveWindow"),
            patch("home_ui.cv2.imshow"),
            patch(
                "home_ui.cv2.waitKey",
                side_effect=click_exit_then_escape,
            ),
            patch("home_ui.cv2.getWindowProperty", return_value=1),
            patch("home_ui.cv2.destroyWindow"),
            patch("home_ui._bring_home_window_to_front"),
        ):
            confirm_exit = unittest.mock.Mock(return_value=False)
            result = show_home_window(confirm_exit=confirm_exit)

        self.assertIs(result, HomeAction.BACKGROUND)
        confirm_exit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
