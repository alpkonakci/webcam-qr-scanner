import unittest
import time
from unittest.mock import patch

import cv2
import numpy as np

from app import parse_args, run_self_test
from camera import CameraConfig
from links import open_web_url, payload_kind
from performance import FPSCounter
from qr_reader import QRResult
from scan_geometry import scan_region, scale_result
from scan_worker import QRScanWorker, ScanGate
from ui import (
    COLOR_ACCENT,
    COLOR_SUCCESS,
    draw_result,
    fps_color,
    is_exit_key,
    readable_preview,
    show_instructions,
)


class AppHelpersTests(unittest.TestCase):
    def test_classifies_http_urls(self) -> None:
        self.assertEqual(payload_kind("https://example.com/path"), "URL")
        self.assertEqual(payload_kind("http://example.com"), "URL")

    def test_does_not_treat_unsafe_scheme_as_web_url(self) -> None:
        self.assertEqual(payload_kind("javascript:alert(1)"), "Text")
        self.assertEqual(payload_kind("file:///C:/secret.txt"), "Text")

    def test_preview_is_single_line_and_bounded(self) -> None:
        preview = readable_preview("satır 1\nsatır 2" + "x" * 100, limit=30)

        self.assertNotIn("\n", preview)
        self.assertLessEqual(len(preview), 30)

    @patch("links.webbrowser.open", return_value=True)
    def test_opens_https_url_in_default_browser(self, browser_open) -> None:
        self.assertTrue(open_web_url("https://example.com/path"))
        browser_open.assert_called_once_with(
            "https://example.com/path", new=2, autoraise=True
        )

    @patch("links.webbrowser.open", return_value=True)
    def test_never_opens_unsafe_scheme(self, browser_open) -> None:
        self.assertFalse(open_web_url("javascript:alert(1)"))
        browser_open.assert_not_called()

    def test_scan_gate_rearms_only_after_code_disappears(self) -> None:
        gate = ScanGate(rearm_seconds=2.0)

        self.assertTrue(gate.should_trigger("same-qr", 10.0))
        self.assertFalse(gate.should_trigger("same-qr", 10.5))
        self.assertFalse(gate.should_trigger("same-qr", 11.0))
        self.assertTrue(gate.should_trigger("same-qr", 13.1))

    def test_default_camera_resolution_is_full_hd(self) -> None:
        config = CameraConfig()

        self.assertEqual((config.width, config.height, config.fps), (1920, 1080, 30))
        self.assertEqual(
            (config.fallback_width, config.fallback_height, config.minimum_fps),
            (1280, 720, 24.0),
        )

    def test_fps_counter_reports_frame_rate(self) -> None:
        counter = FPSCounter(smoothing=0.0)

        counter.tick(1.0)

        self.assertAlmostEqual(counter.tick(1.04), 25.0)

    def test_normal_fps_uses_accent_instead_of_success_green(self) -> None:
        self.assertEqual(fps_color(30.0), COLOR_ACCENT)
        self.assertNotEqual(fps_color(30.0), COLOR_SUCCESS)

    def test_only_escape_key_closes_the_application(self) -> None:
        self.assertTrue(is_exit_key(27))
        self.assertFalse(is_exit_key(ord("q")))
        self.assertFalse(is_exit_key(ord("Q")))

    @patch("sys.argv", ["app.py"])
    def test_closes_after_first_scan_by_default(self) -> None:
        args = parse_args()

        self.assertTrue(args.exit_after_scan)
        self.assertFalse(args.show_fps)

    @patch("sys.argv", ["app.py", "--keep-open"])
    def test_keep_open_option_enables_continuous_scanning(self) -> None:
        args = parse_args()

        self.assertFalse(args.exit_after_scan)

    @patch("sys.argv", ["app.py", "--show-fps"])
    def test_show_fps_option_enables_developer_overlay(self) -> None:
        args = parse_args()

        self.assertTrue(args.show_fps)

    @patch("sys.argv", ["app.py", "--desktop"])
    def test_desktop_option_enables_windowed_error_messages(self) -> None:
        args = parse_args()

        self.assertTrue(args.desktop)

    def test_packaged_self_test_decodes_generated_qr(self) -> None:
        self.assertTrue(run_self_test())

    def test_modern_interface_draws_without_changing_frame_size(self) -> None:
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        original_shape = frame.shape

        show_instructions(frame, animation_time=1.0)

        self.assertEqual(frame.shape, original_shape)
        self.assertGreater(int(frame.sum()), 0)

    def test_result_card_draws_without_changing_frame_size(self) -> None:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        result = QRResult(
            data="https://example.com",
            corners=np.array([[400, 220], [700, 220], [700, 520], [400, 520]]),
        )

        draw_result(frame, result)

        self.assertEqual(frame.shape, (720, 1280, 3))
        self.assertGreater(int(frame.sum()), 0)

    def test_result_coordinates_scale_to_display_resolution(self) -> None:
        result = QRResult(
            data="test",
            corners=np.array([[0, 0], [1920, 0], [1920, 1080], [0, 1080]]),
        )

        scaled = scale_result(result, (1920, 1080), (1280, 720))

        np.testing.assert_array_equal(
            scaled.corners,
            np.array([[0, 0], [1280, 0], [1280, 720], [0, 720]]),
        )

    def test_scan_region_is_centered_square(self) -> None:
        left, top, right, bottom = scan_region((1280, 720))

        self.assertEqual(right - left, bottom - top)
        self.assertAlmostEqual((left + right) / 2, 1280 / 2, delta=1)
        self.assertAlmostEqual((top + bottom) / 2, 720 * 0.54, delta=1)

    @staticmethod
    def _qr_on_frame(value: str, inside: bool) -> np.ndarray:
        encoder = cv2.QRCodeEncoder_create()
        qr_image = encoder.encode(value)
        qr_image = cv2.copyMakeBorder(
            qr_image, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255
        )
        qr_image = cv2.resize(
            qr_image, (240, 240), interpolation=cv2.INTER_NEAREST
        )
        frame = np.full((720, 1280, 3), 255, dtype=np.uint8)
        if inside:
            left, top, right, bottom = scan_region((1280, 720))
            x = (left + right - qr_image.shape[1]) // 2
            y = (top + bottom - qr_image.shape[0]) // 2
        else:
            x, y = 20, 20
        frame[y : y + 240, x : x + 240] = cv2.cvtColor(
            qr_image, cv2.COLOR_GRAY2BGR
        )
        return frame

    @staticmethod
    def _scan_with_worker(frame: np.ndarray) -> list[QRResult] | None:
        version = 0
        results = None
        with QRScanWorker() as worker:
            worker.submit(frame)
            deadline = time.monotonic() + 2.0
            while results is None and time.monotonic() < deadline:
                version, results = worker.poll(version)
                time.sleep(0.01)
        return results

    def test_background_worker_returns_decoded_qr(self) -> None:
        results = self._scan_with_worker(
            self._qr_on_frame("https://example.com/background", inside=True)
        )

        self.assertIsNotNone(results)
        self.assertEqual(results[0].data, "https://example.com/background")

    def test_background_worker_ignores_qr_outside_scan_region(self) -> None:
        results = self._scan_with_worker(
            self._qr_on_frame("https://example.com/outside", inside=False)
        )

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
