import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bridge.pair_management import PairedPhoneSummary
from bridge.pairing import PairingTransportError, PairRevocationError
from exit_codes import (
    CONTROL_MANAGE_PHONES,
    CONTROL_REMOVE_PHONE,
    CONTROL_SCAN_SCREEN,
)
from paired_phone_ipc import RemovePhoneRequest
from tray_app import (
    ChildRole,
    TrayApplication,
    _pairing_error_message,
    create_tray_image,
)


class TrayApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.icon = Mock()
        self.icon.HAS_NOTIFICATION = True
        self.icon.notify = Mock()
        self.icon.stop = Mock()
        self.icon.run = Mock()

    def test_pairing_transport_error_shows_safe_actionable_reason(self) -> None:
        error = PairingTransportError(
            status_code=503,
            code="relay_unavailable",
        )

        message = _pairing_error_message(error)

        self.assertIn("SUPABASE_SECRET_KEY", message)
        self.assertIn("HTTP status: 503", message)
        self.assertNotIn(str(error), message)

    def test_unknown_pairing_error_does_not_echo_remote_code(self) -> None:
        error = PairingTransportError(
            status_code=418,
            code="attacker_controlled_code",
        )

        message = _pairing_error_message(error)

        self.assertIn("relay rejected", message)
        self.assertIn("HTTP status: 418", message)
        self.assertNotIn(error.code, message)

    def _application(
        self,
        process_spawner=None,
        pairing_runner=None,
        pair_manager=None,
        receiver_service=None,
    ) -> TrayApplication:
        process_spawner = process_spawner or Mock()
        if pair_manager is None:
            pair_manager = Mock()
            pair_manager.list_pairs.return_value = ()
        if receiver_service is None:
            receiver_service = Mock()
            receiver_service.has_paired_phones.return_value = False
        with patch("tray_app.pystray.Icon", return_value=self.icon):
            return TrayApplication(
                process_spawner=process_spawner,
                pairing_runner=pairing_runner,
                pair_manager=pair_manager,
                receiver_service=receiver_service,
            )

    def test_generated_icon_has_expected_size_and_visible_content(self) -> None:
        image = create_tray_image(64)

        self.assertEqual(image.size, (64, 64))
        self.assertIsNotNone(image.getbbox())

    def test_phone_menu_switches_to_management_with_current_count(self) -> None:
        pair_manager = Mock()
        pair_manager.list_pairs.return_value = (Mock(), Mock())
        application = self._application(pair_manager=pair_manager)

        self.assertEqual(
            application._phone_menu_text(Mock()),
            "Paired Phones (2)...",
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

        with (
            patch.object(application, "_prepare_for_foreground_dialog") as prepare,
            patch.object(application, "_finish_foreground_dialog") as finish,
        ):
            application._exit_from_menu(self.icon, Mock())

        confirm.assert_called_once_with()
        prepare.assert_called_once_with()
        finish.assert_called_once_with(False)
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

    def test_incoming_security_dialog_cancels_pairing_window_first(self) -> None:
        application = self._application()
        closed = Mock()
        application._pairing_window_closed = closed

        with (
            patch.object(
                application,
                "_dismiss_control_windows",
                return_value=(Mock(),),
            ) as dismiss_windows,
            patch.object(application, "_wait_for_child_exit") as wait_for_exit,
        ):
            application._prepare_for_foreground_dialog()

        self.assertTrue(application._pairing_cancel_event.is_set())
        closed.wait.assert_called_once_with(timeout=1.0)
        wait_for_exit.assert_called_once_with(
            dismiss_windows.return_value[0]
        )

    def test_rejected_security_dialog_restores_home(self) -> None:
        application = self._application()
        application._foreground_dialog_count = 1

        with patch.object(application, "_launch_home") as launch_home:
            application._finish_foreground_dialog(False)

        launch_home.assert_called_once_with()

    def test_opened_browser_does_not_cover_it_with_home(self) -> None:
        application = self._application()
        application._foreground_dialog_count = 1

        with patch.object(application, "_launch_home") as launch_home:
            application._finish_foreground_dialog(True)

        launch_home.assert_not_called()

    def test_full_exit_also_cancels_an_active_pairing_window(self) -> None:
        application = self._application()

        application._stop()

        self.assertTrue(application._pairing_cancel_event.is_set())
        self.icon.stop.assert_called_once_with()

    @patch("tray_app.threading.Thread")
    def test_home_window_is_single_instance(self, thread_type) -> None:
        process = Mock()
        process.poll.return_value = None
        spawner = Mock(return_value=process)
        application = self._application(spawner)

        application._launch_home()
        application._launch_home()

        spawner.assert_called_once_with(
            ["--home-process", "--paired-phone-count", "0"]
        )
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

    def test_dismissed_manager_does_not_reopen_home_over_another_mode(
        self,
    ) -> None:
        process = Mock()
        process.wait.return_value = -15
        application = self._application()
        application._children.add(process)
        application._paired_phones_process = process

        with patch.object(application, "_launch_home") as launch_home:
            application._monitor_child(process, ChildRole.PAIRED_PHONES)

        launch_home.assert_not_called()
        self.assertIsNone(application._paired_phones_process)

    def test_home_screen_action_starts_one_shot_screen_scan(self) -> None:
        application = self._application()

        with patch.object(application, "_launch_screen") as launch_screen:
            application._handle_home_action(CONTROL_SCAN_SCREEN)

        launch_screen.assert_called_once_with()

    @patch("tray_app.threading.Thread")
    @patch("tray_app.write_paired_phones_snapshot")
    def test_home_management_action_opens_single_sanitized_manager_window(
        self,
        write_snapshot,
        thread_type,
    ) -> None:
        summary = PairedPhoneSummary(
            relay_origin="https://relay.example",
            pair_id="abcDEF0123456789-_xyZA",
            short_pair_id="abcDEF…xyZA",
            phone_label="My iPhone",
        )
        pair_manager = Mock()
        pair_manager.list_pairs.return_value = (summary,)
        process = Mock()
        process.poll.return_value = None
        spawner = Mock(return_value=process)
        application = self._application(
            spawner,
            pair_manager=pair_manager,
        )

        application._handle_home_action(CONTROL_MANAGE_PHONES)
        application._launch_paired_phones()

        spawner.assert_called_once_with(["--paired-phones-process"])
        phone = write_snapshot.call_args.args[0][0]
        self.assertEqual(phone.phone_label, "My iPhone")
        self.assertFalse(hasattr(phone, "receiver_token"))
        self.assertFalse(hasattr(phone, "root_key"))
        thread_type.return_value.start.assert_called_once_with()

    @patch("tray_app.consume_phone_removal_request")
    def test_successful_removal_refreshes_receiver_and_home(
        self,
        consume_request,
    ) -> None:
        request = RemovePhoneRequest(
            relay_origin="https://relay.example",
            pair_id="abcDEF0123456789-_xyZA",
            phone_label="My iPhone",
        )
        consume_request.return_value = request
        pair_manager = Mock()
        pair_manager.list_pairs.return_value = ()
        pair_manager.remove_pair.return_value = SimpleNamespace(
            summary=SimpleNamespace(phone_label="My iPhone")
        )
        receiver = Mock()
        receiver.has_paired_phones.return_value = True
        application = self._application(
            pair_manager=pair_manager,
            receiver_service=receiver,
        )

        with (
            patch.object(application, "_refresh_pairing_status"),
            patch.object(application, "_launch_home") as launch_home,
        ):
            application._handle_paired_phones_action(CONTROL_REMOVE_PHONE)

        pair_manager.remove_pair.assert_called_once_with(
            relay_origin=request.relay_origin,
            pair_id=request.pair_id,
        )
        receiver.request_refresh.assert_called_once_with()
        launch_home.assert_called_once_with()

    @patch("tray_app.consume_phone_removal_request")
    def test_remote_failure_falls_back_to_local_cleanup_after_one_approval(
        self,
        consume_request,
    ) -> None:
        request = RemovePhoneRequest(
            relay_origin="https://relay.example",
            pair_id="abcDEF0123456789-_xyZA",
            phone_label="My iPhone",
        )
        consume_request.return_value = request
        pair_manager = Mock()
        pair_manager.list_pairs.return_value = ()
        pair_manager.remove_pair.side_effect = PairRevocationError(
            code="network_error"
        )
        pair_manager.forget_local_pair.return_value = SimpleNamespace(
            summary=SimpleNamespace(phone_label="My iPhone")
        )
        receiver = Mock()
        receiver.has_paired_phones.return_value = True
        application = self._application(
            pair_manager=pair_manager,
            receiver_service=receiver,
        )

        with (
            patch.object(application, "_refresh_pairing_status"),
            patch.object(application, "_launch_home"),
        ):
            application._remove_requested_phone()

        pair_manager.remove_pair.assert_called_once_with(
            relay_origin=request.relay_origin,
            pair_id=request.pair_id,
        )
        pair_manager.forget_local_pair.assert_called_once_with(
            relay_origin=request.relay_origin,
            pair_id=request.pair_id,
        )
        receiver.request_refresh.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
