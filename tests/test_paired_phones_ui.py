from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from paired_phone_ipc import PairedPhoneView
from paired_phones_ui import (
    REMOVE_BOUNDS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    PairedPhonesAction,
    abbreviated_pair_id,
    action_at_point,
    build_paired_phones_canvas,
    row_at_point,
    show_paired_phones_window,
)


class PairedPhonesUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.phone = PairedPhoneView(
            relay_origin="https://relay.example",
            pair_id="abcDEF0123456789-_xyZA",
            phone_label="My iPhone",
        )

    def test_pair_identifier_is_always_abbreviated(self) -> None:
        short = abbreviated_pair_id(self.phone.pair_id)

        self.assertEqual(short, "abcDEF…xyZA")
        self.assertNotEqual(short, self.phone.pair_id)

    def test_rows_and_remove_button_have_explicit_targets(self) -> None:
        left, top, right, bottom = REMOVE_BOUNDS
        remove_x = (left + right) // 2
        remove_y = (top + bottom) // 2
        self.assertEqual(
            row_at_point(100, 120, phone_count=2, scroll_offset=0),
            0,
        )
        self.assertIsNone(
            action_at_point(remove_x, remove_y, has_selection=False)
        )
        self.assertIs(
            action_at_point(remove_x, remove_y, has_selection=True),
            PairedPhonesAction.REMOVE,
        )

    def test_canvas_has_stable_size(self) -> None:
        canvas = build_paired_phones_canvas(
            (self.phone,),
            selected_index=0,
        )

        self.assertEqual(canvas.shape, (WINDOW_HEIGHT, WINDOW_WIDTH, 3))
        self.assertEqual(canvas.dtype, np.uint8)

    def test_remove_requires_confirmation_with_short_identifier(self) -> None:
        callback = None

        def remember_callback(_: str, value) -> None:
            nonlocal callback
            callback = value

        call_count = 0

        def select_then_remove(_: int) -> int:
            nonlocal call_count
            call_count += 1
            assert callback is not None
            if call_count == 1:
                callback(cv2.EVENT_LBUTTONUP, 100, 120, 0, None)
            elif call_count == 2:
                left, top, right, bottom = REMOVE_BOUNDS
                callback(
                    cv2.EVENT_LBUTTONUP,
                    (left + right) // 2,
                    (top + bottom) // 2,
                    0,
                    None,
                )
            return -1

        confirm = Mock(return_value=True)
        with (
            patch("paired_phones_ui.cv2.namedWindow"),
            patch(
                "paired_phones_ui.cv2.setMouseCallback",
                side_effect=remember_callback,
            ),
            patch("paired_phones_ui.cv2.moveWindow"),
            patch("paired_phones_ui.cv2.imshow"),
            patch(
                "paired_phones_ui.cv2.waitKey",
                side_effect=select_then_remove,
            ),
            patch("paired_phones_ui.cv2.getWindowProperty", return_value=1),
            patch("paired_phones_ui.cv2.destroyWindow"),
            patch("paired_phones_ui._bring_window_to_front"),
        ):
            decision = show_paired_phones_window(
                (self.phone,),
                confirm_remove=confirm,
            )

        self.assertIs(decision.action, PairedPhonesAction.REMOVE)
        self.assertEqual(decision.phone, self.phone)
        confirm.assert_called_once_with("My iPhone", "abcDEF…xyZA")

    def test_escape_returns_to_control_center(self) -> None:
        with (
            patch("paired_phones_ui.cv2.namedWindow"),
            patch("paired_phones_ui.cv2.setMouseCallback"),
            patch("paired_phones_ui.cv2.moveWindow"),
            patch("paired_phones_ui.cv2.imshow"),
            patch("paired_phones_ui.cv2.waitKey", return_value=27),
            patch("paired_phones_ui.cv2.destroyWindow"),
            patch("paired_phones_ui._bring_window_to_front"),
        ):
            decision = show_paired_phones_window((self.phone,))

        self.assertIs(decision.action, PairedPhonesAction.BACK)


if __name__ == "__main__":
    unittest.main()
