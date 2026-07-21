import unittest
from unittest.mock import Mock, patch

from camera import CameraConfig, CameraStream


class CameraSelectionTests(unittest.TestCase):
    @patch("camera.cv2.VideoCapture")
    def test_keeps_full_hd_when_target_fps_is_available(self, video_capture) -> None:
        capture = Mock()
        capture.isOpened.return_value = True
        video_capture.return_value = capture
        stream = CameraStream(CameraConfig())

        with patch.object(
            stream,
            "_configure_and_measure",
            return_value=((1920, 1080), 29.5),
        ) as configure:
            stream.open()

        self.assertEqual(stream.resolution, (1920, 1080))
        self.assertEqual(configure.call_count, 1)
        stream.release()

    @patch("camera.cv2.VideoCapture")
    def test_falls_back_to_720p_when_full_hd_is_too_slow(self, video_capture) -> None:
        capture = Mock()
        capture.isOpened.return_value = True
        video_capture.return_value = capture
        stream = CameraStream(CameraConfig())

        with patch.object(
            stream,
            "_configure_and_measure",
            side_effect=[
                ((1920, 1080), 18.0),
                ((1280, 720), 30.0),
            ],
        ) as configure:
            stream.open()

        self.assertEqual(stream.resolution, (1280, 720))
        self.assertEqual(stream.measured_fps, 30.0)
        self.assertEqual(configure.call_count, 2)
        stream.release()


if __name__ == "__main__":
    unittest.main()
