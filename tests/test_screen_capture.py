import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from screen_capture import (
    ConnectedDisplay,
    SM_CXVIRTUALSCREEN,
    SM_CYVIRTUALSCREEN,
    SM_XVIRTUALSCREEN,
    SM_YVIRTUALSCREEN,
    ScreenCaptureError,
    ScreenBounds,
    capture_display,
    capture_display_dxgi,
    is_probably_blanked_frame,
    number_connected_displays,
    virtual_screen_bounds,
)


class ScreenBoundsTests(unittest.TestCase):
    def test_numbers_displays_in_windows_device_order(self) -> None:
        displays = number_connected_displays(
            [
                ("\\\\.\\DISPLAY2", ScreenBounds(1920, 0, 1280, 1024), False),
                ("\\\\.\\DISPLAY1", ScreenBounds(0, 0, 1920, 1080), True),
            ]
        )

        self.assertEqual(
            displays,
            (
                ConnectedDisplay(
                    1,
                    "\\\\.\\DISPLAY1",
                    ScreenBounds(0, 0, 1920, 1080),
                    True,
                ),
                ConnectedDisplay(
                    2,
                    "\\\\.\\DISPLAY2",
                    ScreenBounds(1920, 0, 1280, 1024),
                    False,
                ),
            ),
        )

    def test_reads_multi_monitor_virtual_desktop_with_negative_origin(self) -> None:
        metrics = {
            SM_XVIRTUALSCREEN: -1920,
            SM_YVIRTUALSCREEN: 0,
            SM_CXVIRTUALSCREEN: 3840,
            SM_CYVIRTUALSCREEN: 1080,
        }

        bounds = virtual_screen_bounds(metrics.__getitem__)

        self.assertEqual((bounds.left, bounds.top), (-1920, 0))
        self.assertEqual((bounds.width, bounds.height), (3840, 1080))

    def test_rejects_invalid_virtual_desktop_size(self) -> None:
        metrics = {
            SM_XVIRTUALSCREEN: 0,
            SM_YVIRTUALSCREEN: 0,
            SM_CXVIRTUALSCREEN: 0,
            SM_CYVIRTUALSCREEN: 1080,
        }

        with self.assertRaises(ScreenCaptureError):
            virtual_screen_bounds(metrics.__getitem__)

    def test_dxgi_capture_maps_the_exact_windows_display_name(self) -> None:
        frame = np.full((60, 80, 3), 127, dtype=np.uint8)
        camera = Mock()
        camera.grab.return_value = frame
        dxcam_module = SimpleNamespace(
            create=Mock(return_value=camera),
            __factory=SimpleNamespace(
                outputs=[
                    [SimpleNamespace(devicename="\\\\.\\DISPLAY1")],
                    [SimpleNamespace(devicename="\\\\.\\DISPLAY2")],
                ]
            ),
        )
        display = ConnectedDisplay(
            2,
            "\\\\.\\DISPLAY2",
            ScreenBounds(1920, 0, 80, 60),
        )

        result = capture_display_dxgi(display, dxcam_module=dxcam_module)

        np.testing.assert_array_equal(result, frame)
        dxcam_module.create.assert_called_once_with(
            device_idx=1,
            output_idx=0,
            output_color="BGR",
            backend="dxgi",
            processor_backend="cv2",
        )
        camera.grab.assert_called_once_with(new_frame_only=False)
        camera.release.assert_called_once_with()

    def test_selected_display_falls_back_to_gdi_when_dxgi_fails(self) -> None:
        display = ConnectedDisplay(
            2,
            "\\\\.\\DISPLAY2",
            ScreenBounds(1920, 0, 80, 60),
        )
        fallback = np.full((60, 80, 3), 42, dtype=np.uint8)

        with (
            patch(
                "screen_capture.capture_display_dxgi",
                side_effect=ScreenCaptureError("DXGI unavailable"),
            ),
            patch(
                "screen_capture.capture_screen_bounds",
                return_value=fallback,
            ) as gdi_capture,
        ):
            result = capture_display(display)

        np.testing.assert_array_equal(result, fallback)
        gdi_capture.assert_called_once_with(display.bounds)

    def test_recognizes_a_blanked_protected_surface(self) -> None:
        self.assertTrue(
            is_probably_blanked_frame(np.zeros((60, 80, 3), dtype=np.uint8))
        )
        self.assertFalse(
            is_probably_blanked_frame(np.full((60, 80, 3), 30, dtype=np.uint8))
        )


if __name__ == "__main__":
    unittest.main()
