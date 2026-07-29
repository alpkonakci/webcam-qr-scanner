import unittest
from unittest.mock import Mock, patch

import launcher
from exit_codes import APPLICATION_EXIT_REQUESTED, CAMERA_CLOSED


class LauncherTests(unittest.TestCase):
    def test_default_launch_starts_tray_and_opens_camera(self) -> None:
        with patch("launcher.run_bridge", return_value=0) as run_bridge:
            result = launcher.main(["--show-fps"])

        self.assertEqual(result, 0)
        run_bridge.assert_called_once_with(
            open_camera=True,
            camera_arguments=["--show-fps"],
        )

    def test_screen_mode_bypasses_camera_tray(self) -> None:
        with patch("launcher.run_screen", return_value=0) as run_screen:
            result = launcher.main(["--screen", "--desktop"])

        self.assertEqual(result, 0)
        run_screen.assert_called_once_with(["--desktop"])

    def test_self_test_does_not_emit_camera_lifecycle_signal(self) -> None:
        with patch("launcher.run_camera", return_value=0) as run_camera:
            result = launcher.main(["--self-test"])

        self.assertEqual(result, 0)
        run_camera.assert_called_once_with(
            ["--self-test"],
            signal_controller=False,
        )

    @patch("launcher.request_open_camera")
    @patch("launcher.BridgeInstanceGuard")
    def test_second_launch_asks_existing_tray_to_open_camera(
        self,
        guard_type,
        request_open_camera,
    ) -> None:
        guard = Mock(already_running=True)
        guard_type.return_value.__enter__.return_value = guard

        result = launcher.run_bridge(
            open_camera=True,
            camera_arguments=["--camera", "1"],
        )

        self.assertEqual(result, 0)
        request_open_camera.assert_called_once_with(["--camera", "1"])

    @patch("launcher.request_camera_closed")
    @patch("launcher.request_bridge_exit")
    @patch("app.main", return_value=CAMERA_CLOSED)
    def test_camera_close_notifies_background_controller(
        self,
        camera_main,
        request_bridge_exit,
        request_camera_closed,
    ) -> None:
        result = launcher.run_camera(["--desktop"])

        self.assertEqual(result, CAMERA_CLOSED)
        camera_main.assert_called_once_with(["--desktop"])
        request_camera_closed.assert_called_once_with()
        request_bridge_exit.assert_not_called()

    @patch("launcher.request_camera_closed")
    @patch("launcher.request_bridge_exit")
    @patch("app.main", return_value=APPLICATION_EXIT_REQUESTED)
    def test_full_exit_requests_background_controller_shutdown(
        self,
        camera_main,
        request_bridge_exit,
        request_camera_closed,
    ) -> None:
        result = launcher.run_camera(["--desktop"])

        self.assertEqual(result, APPLICATION_EXIT_REQUESTED)
        request_bridge_exit.assert_called_once_with()
        request_camera_closed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
