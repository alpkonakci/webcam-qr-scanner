import unittest
from unittest.mock import patch

from paired_phone_ipc import PairedPhoneView
from paired_phones_ui import PairedPhonesAction, PairedPhonesDecision
from phone_scanner_ui import build_phone_scanner_canvas, show_phone_scanner_window
from qr_reader import QRReader


class PhoneScannerUiTests(unittest.TestCase):
    def test_recovery_qr_contains_only_public_homepage(self):
        canvas = build_phone_scanner_canvas("https://qrwebcam.vercel.app")
        self.assertEqual(canvas.shape, (600, 574, 3))
        results = QRReader().scan_all(canvas[98:448, 112:462])
        self.assertEqual([r.data for r in results], ["https://qrwebcam.vercel.app/"])

    def test_return_scanner_does_not_start_pairing_or_remove_access(self):
        from launcher import run_paired_phones
        phones = (PairedPhoneView("https://qrwebcam.vercel.app", "test-pair", "Phone"),)
        with (
            patch("paired_phone_ipc.consume_paired_phones_snapshot", return_value=phones),
            patch("paired_phones_ui.show_paired_phones_window", side_effect=[
                PairedPhonesDecision(PairedPhonesAction.OPEN_SCANNER),
                PairedPhonesDecision(PairedPhonesAction.BACK),
            ]) as window,
            patch("phone_scanner_ui.show_phone_scanner_window") as show,
            patch("paired_phone_ipc.request_phone_removal") as remove,
        ):
            run_paired_phones()
        self.assertEqual(window.call_count, 2)
        show.assert_called_once_with("https://qrwebcam.vercel.app")
        remove.assert_not_called()

    def test_escape_closes_recovery_window(self):
        with (
            patch("phone_scanner_ui.cv2.namedWindow"),
            patch("phone_scanner_ui.set_window_icon"),
            patch("phone_scanner_ui.cv2.setMouseCallback"),
            patch("phone_scanner_ui.cv2.moveWindow"),
            patch("phone_scanner_ui.cv2.imshow"),
            patch("phone_scanner_ui._bring_window_to_front"),
            patch("phone_scanner_ui.cv2.waitKey", return_value=27),
            patch("phone_scanner_ui.cv2.destroyWindow") as destroy,
        ):
            show_phone_scanner_window("https://qrwebcam.vercel.app")
        destroy.assert_called_once()
