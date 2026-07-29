import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app_settings import SettingsStore
from tray_app import TrayApplication, create_tray_image


class TrayApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.settings_store = SettingsStore(
            Path(self.temporary_directory.name) / "settings.json"
        )
        self.icon = Mock()
        self.icon.HAS_NOTIFICATION = True
        self.icon.notify = Mock()
        self.icon.stop = Mock()
        self.icon.run = Mock()

    def _application(self, process_spawner=None) -> TrayApplication:
        process_spawner = process_spawner or Mock()
        with patch("tray_app.pystray.Icon", return_value=self.icon):
            return TrayApplication(
                settings_store=self.settings_store,
                process_spawner=process_spawner,
            )

    def test_generated_icon_has_expected_size_and_visible_content(self) -> None:
        image = create_tray_image(64)

        self.assertEqual(image.size, (64, 64))
        self.assertIsNotNone(image.getbbox())

    def test_camera_closed_notification_is_shown_only_once(self) -> None:
        application = self._application()

        application._show_camera_closed_notice_once()
        application._show_camera_closed_notice_once()

        self.icon.notify.assert_called_once()
        self.assertTrue(
            self.settings_store.load().camera_closed_notice_shown
        )

    def test_failed_notification_is_not_recorded_as_shown(self) -> None:
        self.icon.HAS_NOTIFICATION = False
        application = self._application()

        application._show_camera_closed_notice_once()

        self.icon.notify.assert_not_called()
        self.assertFalse(
            self.settings_store.load().camera_closed_notice_shown
        )

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


if __name__ == "__main__":
    unittest.main()
