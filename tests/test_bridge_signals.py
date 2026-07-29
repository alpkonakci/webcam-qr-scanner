import tempfile
import unittest
from pathlib import Path

from bridge_signals import (
    clear_control_requests,
    consume_bridge_exit_request,
    consume_camera_closed,
    consume_open_camera_request,
    request_bridge_exit,
    request_camera_closed,
    request_open_camera,
)


class BridgeSignalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)

    def test_each_control_signal_is_consumed_once(self) -> None:
        cases = (
            (request_bridge_exit, consume_bridge_exit_request),
            (request_camera_closed, consume_camera_closed),
        )
        for request, consume in cases:
            with self.subTest(request=request.__name__):
                request(self.directory)
                self.assertTrue(consume(self.directory))
                self.assertFalse(consume(self.directory))

    def test_camera_request_preserves_launcher_arguments(self) -> None:
        request_open_camera(["--camera", "1"], self.directory)

        self.assertEqual(
            consume_open_camera_request(self.directory),
            ["--camera", "1"],
        )
        self.assertIsNone(consume_open_camera_request(self.directory))

    def test_clear_removes_all_stale_requests(self) -> None:
        request_bridge_exit(self.directory)
        request_open_camera(directory=self.directory)
        request_camera_closed(self.directory)

        clear_control_requests(self.directory)

        self.assertFalse(consume_bridge_exit_request(self.directory))
        self.assertIsNone(consume_open_camera_request(self.directory))
        self.assertFalse(consume_camera_closed(self.directory))


if __name__ == "__main__":
    unittest.main()
