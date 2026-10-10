import unittest

import numpy as np

from screen_selector import (
    HEADER_HEIGHT,
    build_region_selector_canvas,
    crop_screen_region,
    map_preview_region_to_source,
    normalize_preview_region,
    selector_preview_size,
)


class ScreenSelectorTests(unittest.TestCase):
    def test_preview_preserves_ultrawide_virtual_desktop_ratio(self) -> None:
        self.assertEqual(
            selector_preview_size((3840, 1080), (1600, 900)),
            (1600, 450),
        )

    def test_drag_rectangle_is_normalized_and_clamped(self) -> None:
        region = normalize_preview_region(
            (520, 260),
            (-20, 40),
            (500, 300),
        )

        self.assertEqual(region, (0, 40, 500, 260))

    def test_tiny_drag_is_not_accepted(self) -> None:
        self.assertIsNone(
            normalize_preview_region((10, 10), (15, 18), (500, 300))
        )

    def test_preview_region_maps_back_to_source_pixels(self) -> None:
        source_region = map_preview_region_to_source(
            (100, 50, 300, 200),
            (2000, 1000),
            (1000, 500),
        )

        self.assertEqual(source_region, (200, 100, 600, 400))

    def test_crop_returns_only_selected_source_area(self) -> None:
        frame = np.arange(100 * 200 * 3, dtype=np.int32).reshape(100, 200, 3)

        crop = crop_screen_region(
            frame,
            (25, 10, 75, 40),
            (100, 50),
        )

        np.testing.assert_array_equal(crop, frame[20:80, 50:150])
        self.assertFalse(np.shares_memory(crop, frame))

    def test_selector_canvas_keeps_capture_in_memory_and_draws_region(self) -> None:
        frame = np.zeros((300, 600, 3), dtype=np.uint8)

        canvas, preview_size = build_region_selector_canvas(
            frame,
            selection=(100, 80, 300, 220),
            window_limit=(600, 500),
        )

        self.assertEqual(preview_size, (600, 300))
        self.assertEqual(canvas.shape, (300 + HEADER_HEIGHT, 600, 3))
        self.assertGreater(int(canvas.sum()), 0)
        self.assertEqual(int(frame.sum()), 0)


if __name__ == "__main__":
    unittest.main()
