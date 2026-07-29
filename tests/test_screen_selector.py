import unittest

import numpy as np

from qr_reader import QRResult
from screen_selector import (
    HEADER_HEIGHT,
    build_selector_canvas,
    display_results,
    nearest_result_index,
    result_index_at_point,
    result_label,
    selector_preview_size,
)


def _result(
    value: str,
    left: int,
    top: int,
    size: int = 100,
) -> QRResult:
    return QRResult(
        value,
        np.array(
            [
                [left, top],
                [left + size, top],
                [left + size, top + size],
                [left, top + size],
            ],
            dtype=np.int32,
        ),
    )


class ScreenSelectorTests(unittest.TestCase):
    def test_preview_preserves_ultrawide_virtual_desktop_ratio(self) -> None:
        self.assertEqual(
            selector_preview_size((3840, 1080), (1600, 900)),
            (1600, 450),
        )

    def test_result_coordinates_include_header_offset(self) -> None:
        mapped = display_results(
            [_result("https://example.com", 100, 100)],
            (1000, 500),
            (500, 250),
        )

        np.testing.assert_array_equal(
            mapped[0].corners,
            np.array(
                [
                    [50, 50 + HEADER_HEIGHT],
                    [100, 50 + HEADER_HEIGHT],
                    [100, 100 + HEADER_HEIGHT],
                    [50, 100 + HEADER_HEIGHT],
                ]
            ),
        )

    def test_nearest_result_is_hover_feedback_only(self) -> None:
        results = [
            _result("https://one.example", 10, 10),
            _result("https://two.example", 400, 10),
        ]

        self.assertEqual(nearest_result_index(results, (430, 50)), 1)

    def test_click_must_be_inside_padded_qr_bounds(self) -> None:
        results = [
            _result("https://one.example", 20, 20),
            _result("https://two.example", 300, 20),
        ]

        self.assertEqual(result_index_at_point(results, (330, 50)), 1)
        self.assertIsNone(result_index_at_point(results, (200, 250)))

    def test_url_label_shows_hostname_without_full_path(self) -> None:
        label = result_label(
            _result("https://example.com/private/path", 0, 0),
            2,
        )

        self.assertEqual(label, "2  example.com")
        self.assertNotIn("private", label)

    def test_selector_canvas_keeps_frame_in_memory_and_draws_markers(self) -> None:
        frame = np.zeros((300, 600, 3), dtype=np.uint8)
        result = _result("https://example.com", 100, 100)

        canvas, mapped = build_selector_canvas(
            frame,
            [result],
            hover_index=0,
            window_limit=(600, 500),
        )

        self.assertEqual(canvas.shape, (300 + HEADER_HEIGHT, 600, 3))
        self.assertEqual(len(mapped), 1)
        self.assertGreater(int(canvas.sum()), 0)
        self.assertEqual(int(frame.sum()), 0)


if __name__ == "__main__":
    unittest.main()
