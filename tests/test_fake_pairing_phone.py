from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bridge.fake_pairing_phone import find_visible_pairing_uri


class FakePairingPhoneTests(unittest.TestCase):
    @patch("bridge.fake_pairing_phone.QRReader")
    @patch("bridge.fake_pairing_phone.capture_virtual_screen")
    def test_requires_one_unique_visible_pairing_qr(
        self,
        capture,
        reader_type,
    ) -> None:
        capture.return_value = Mock()
        reader_type.return_value.scan_all.return_value = [
            SimpleNamespace(data="https://example.com"),
            SimpleNamespace(data="wqrs://pair?test=one"),
            SimpleNamespace(data="wqrs://pair?test=one"),
        ]

        self.assertEqual(
            find_visible_pairing_uri(),
            "wqrs://pair?test=one",
        )

    @patch("bridge.fake_pairing_phone.QRReader")
    @patch("bridge.fake_pairing_phone.capture_virtual_screen")
    def test_refuses_ambiguous_pairing_qrs(self, capture, reader_type) -> None:
        capture.return_value = Mock()
        reader_type.return_value.scan_all.return_value = [
            SimpleNamespace(data="wqrs://pair?test=one"),
            SimpleNamespace(data="wqrs://pair?test=two"),
        ]

        with self.assertRaisesRegex(RuntimeError, "Multiple"):
            find_visible_pairing_uri()


if __name__ == "__main__":
    unittest.main()
