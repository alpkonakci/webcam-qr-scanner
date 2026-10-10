from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paired_phone_ipc import (
    PAIRED_PHONES_SNAPSHOT_FILENAME,
    REMOVE_PHONE_REQUEST_FILENAME,
    PairedPhoneView,
    consume_paired_phones_snapshot,
    consume_phone_removal_request,
    request_phone_removal,
    write_paired_phones_snapshot,
)


class PairedPhoneIpcTests(unittest.TestCase):
    def setUp(self) -> None:
        self.phone = PairedPhoneView(
            relay_origin="https://relay.example",
            pair_id="abcDEF0123456789-_xyZA",
            phone_label="My iPhone",
        )

    def test_snapshot_contains_only_non_secret_view_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_paired_phones_snapshot((self.phone,), path)

            raw = json.loads(
                (path / PAIRED_PHONES_SNAPSHOT_FILENAME).read_text("utf-8")
            )

            self.assertEqual(
                set(raw[0]),
                {"relay_origin", "pair_id", "phone_label"},
            )
            self.assertNotIn("token", json.dumps(raw).lower())
            self.assertNotIn("root_key", json.dumps(raw).lower())
            self.assertEqual(consume_paired_phones_snapshot(path), (self.phone,))
            self.assertFalse((path / PAIRED_PHONES_SNAPSHOT_FILENAME).exists())

    def test_removal_request_round_trips_locator_and_is_one_use(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            request_phone_removal(self.phone, path)

            request = consume_phone_removal_request(path)

            self.assertIsNotNone(request)
            assert request is not None
            self.assertEqual(request.pair_id, self.phone.pair_id)
            self.assertEqual(request.phone_label, "My iPhone")
            self.assertIsNone(consume_phone_removal_request(path))

    def test_extra_credential_field_invalidates_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / REMOVE_PHONE_REQUEST_FILENAME).write_text(
                json.dumps(
                    {
                        "relay_origin": self.phone.relay_origin,
                        "pair_id": self.phone.pair_id,
                        "phone_label": self.phone.phone_label,
                        "receiver_token": "must-not-cross-ui-boundary",
                    }
                ),
                encoding="utf-8",
            )

            self.assertIsNone(consume_phone_removal_request(path))


if __name__ == "__main__":
    unittest.main()
