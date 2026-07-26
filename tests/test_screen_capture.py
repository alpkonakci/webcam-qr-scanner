import unittest

from screen_capture import (
    SM_CXVIRTUALSCREEN,
    SM_CYVIRTUALSCREEN,
    SM_XVIRTUALSCREEN,
    SM_YVIRTUALSCREEN,
    ScreenCaptureError,
    virtual_screen_bounds,
)


class ScreenBoundsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
