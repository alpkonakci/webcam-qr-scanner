import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from exit_codes import CONTROL_SCAN_SCREEN
from tray_app import ChildRole, TrayApplication, create_tray_image


class TrayApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.icon = Mock()
        self.icon.HAS_NOTIFICATION = True
        self.icon.notify = Mock()
        self.icon.stop = Mock()
        self.icon.run = Mock()

    def _application(
        self,
        process_spawner=None,
        pairing_runner=None,
    ) -> TrayApplication:
        process_spawner = process_spawner or Mock()
        with patch("tray_app.pystray.Icon", return_value=self.icon):
            return TrayApplication(
                process_spawner=process_spawner,
                pairing_runner=pairing_runner,
            )

    def test_generated_icon_has_expected_size_and_visible_content(self) -> None:
        image = create_tray_image(64)

        self.assertEqual(image.size, (64, 64))
        self.assertIsNotNone(image.getbbox())

    @patch("tray_app.threading.Thread")
    def test_repeated_camera_action_does_not_open_second_process(
        self,
        thread_type,
    ) -> None:
        process = Mock()
        process.poll.return_value = None
        spawner = Mock(return_value=process)
        application = self._application(spawner)

        application._launch_camera()
        application._launch_camera()

        spawner.assert_called_once()
        self.icon.notify.assert_called_once_with(
            "The camera scanner is already open.",
            "QR Scanner",
        )
        thread_type.return_value.start.assert_called_once_with()

    @patch("tray_app.threading.Thread")
    def test_requested_camera_arguments_are_forwarded(self, thread_type) -> None:
        process = Mock()
        process.poll.return_value = None
        spawner = Mock(return_value=process)
        application = self._application(spawner)

        application._launch_camera(["--camera", "1", "--show-fps"])

        spawner.assert_called_once_with(
            [
                "--camera-process",
                "--desktop",
                "--camera",
                "1",
                "--show-fps",
            ]
        )
        thread_type.return_value.start.assert_called_once_with()

    @patch("tray_app.confirm_application_exit", return_value=False)
    def test_cancelled_exit_keeps_tray_running(self, confirm) -> None:
        application = self._application()

        application._exit_from_menu(self.icon, Mock())

        confirm.assert_called_once_with()
        self.icon.stop.assert_not_called()

    def test_approved_pairing_notifies_with_verified_phone_label(self) -> None:
        result = SimpleNamespace(
            status=SimpleNamespace(value="approved"),
            phone_label="My iPhone",
        )
        application = self._application(pairing_runner=Mock(return_value=result))

        with patch.object(application, "_launch_home") as launch_home:
            application._run_pairing()

        self.icon.notify.assert_called_once_with(
            "My iPhone was paired securely.",
            "QR Scanner",
        )
        launch_home.assert_called_once_with()

    def test_second_pairing_action_does_not_open_another_window(self) -> None:
        application = self._application(pairing_runner=Mock())
        active_thread = Mock()
        active_thread.is_alive.return_value = True
        application._pairing_thread = active_thread

        application._pair_phone(self.icon, Mock())

        self.icon.notify.assert_called_once_with(
            "A phone pairing window is already open.",
            "QR Scanner",
        )

    @patch("tray_app.threading.Thread")
    def test_home_window_is_single_instance(self, thread_type) -> None:
        process = Mock()
        process.poll.return_value = None
        spawner = Mock(return_value=process)
        application = self._application(spawner)

        application._launch_home()
        application._launch_home()

        spawner.assert_called_once_with(["--home-process"])
        thread_type.return_value.start.assert_called_once_with()

    def test_camera_process_return_reopens_home(self) -> None:
        process = Mock()
        process.wait.return_value = 0
        application = self._application()
        application._children.add(process)
        application._camera_process = process

        with patch.object(application, "_launch_home") as launch_home:
            application._monitor_child(process, ChildRole.CAMERA)

        launch_home.assert_called_once_with()
        self.assertIsNone(application._camera_process)

    def test_home_screen_action_starts_one_shot_screen_scan(self) -> None:
        application = self._application()

        with patch.object(application, "_launch_screen") as launch_screen:
            application._handle_home_action(CONTROL_SCAN_SCREEN)

        launch_screen.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
