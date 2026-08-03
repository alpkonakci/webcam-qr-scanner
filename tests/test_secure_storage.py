from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from bridge.protocol import random_b64url
from bridge.realtime import RealtimeSession
from bridge.secure_storage import (
    DpapiProtector,
    PairingStore,
    RelayDevice,
    SecureStorageError,
    StoredPair,
)


class XorTestProtector:
    """Deterministic test double; it is deliberately not production crypto."""

    def protect(self, plaintext: bytes) -> bytes:
        return bytes(value ^ 0xA5 for value in plaintext)

    def unprotect(self, ciphertext: bytes) -> bytes:
        return bytes(value ^ 0xA5 for value in ciphertext)


class PairingStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "phone-to-pc.dat"
        self.store = PairingStore(
            self.path,
            protector=XorTestProtector(),
        )
        self.device = RelayDevice(
            relay_origin="https://relay.example",
            device_id=random_b64url(16),
            receiver_token=random_b64url(32),
        )

    def test_missing_store_is_empty(self) -> None:
        snapshot = self.store.load()
        self.assertEqual(snapshot.devices, ())
        self.assertEqual(snapshot.pairs, ())

    def test_device_and_pair_round_trip_without_plaintext_on_disk(self) -> None:
        self.store.replace_device(self.device, clear_pairs=False)
        pair = StoredPair(
            relay_origin=self.device.relay_origin,
            device_id=self.device.device_id,
            pair_id=random_b64url(16),
            root_key=os.urandom(32),
            phone_label="My iPhone",
        )
        self.store.add_pair(pair)

        snapshot = self.store.load()
        self.assertEqual(snapshot.device_for(self.device.relay_origin), self.device)
        self.assertEqual(snapshot.pairs_for(self.device.relay_origin), (pair,))
        protected = self.path.read_bytes()
        self.assertNotIn(self.device.receiver_token.encode("ascii"), protected)
        self.assertNotIn(pair.pair_id.encode("ascii"), protected)
        self.assertNotIn(pair.root_key, protected)
        self.assertNotIn(pair.phone_label.encode("utf-8"), protected)

    def test_corrupted_ciphertext_fails_closed(self) -> None:
        self.path.write_bytes(b"not a protected credential store")
        with self.assertRaises(SecureStorageError):
            self.store.load()

    def test_pair_requires_matching_relay_device(self) -> None:
        pair = StoredPair(
            relay_origin=self.device.relay_origin,
            device_id=self.device.device_id,
            pair_id=random_b64url(16),
            root_key=os.urandom(32),
            phone_label="Phone",
        )
        with self.assertRaises(SecureStorageError):
            self.store.add_pair(pair)

    def test_replacing_device_clears_obsolete_pairs_explicitly(self) -> None:
        self.store.replace_device(self.device, clear_pairs=False)
        self.store.add_pair(
            StoredPair(
                relay_origin=self.device.relay_origin,
                device_id=self.device.device_id,
                pair_id=random_b64url(16),
                root_key=os.urandom(32),
                phone_label="Phone",
            )
        )
        replacement = RelayDevice(
            relay_origin=self.device.relay_origin,
            device_id=random_b64url(16),
            receiver_token=random_b64url(32),
        )

        with self.assertRaises(SecureStorageError):
            self.store.replace_device(replacement, clear_pairs=False)
        snapshot = self.store.replace_device(replacement, clear_pairs=True)
        self.assertEqual(snapshot.devices, (replacement,))
        self.assertEqual(snapshot.pairs, ())

    def test_realtime_session_is_rotated_inside_protected_store(self) -> None:
        self.store.replace_device(self.device, clear_pairs=False)
        session = RealtimeSession(
            access_token="a" * 80,
            refresh_token="r" * 48,
            expires_at=int(time.time()) + 3600,
            user_id="3f25129c-8558-4bdf-a37d-e70b650e25b1",
        )

        snapshot = self.store.update_realtime_session(
            self.device.relay_origin,
            session,
        )

        stored = snapshot.device_for(self.device.relay_origin)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.realtime_access_token, session.access_token)
        self.assertEqual(stored.realtime_refresh_token, session.refresh_token)
        protected = self.path.read_bytes()
        self.assertNotIn(session.access_token.encode("ascii"), protected)
        self.assertNotIn(session.refresh_token.encode("ascii"), protected)


@unittest.skipUnless(os.name == "nt", "Windows DPAPI test")
class DpapiProtectorTests(unittest.TestCase):
    def test_current_user_round_trip(self) -> None:
        protector = DpapiProtector()
        plaintext = b"wqrs DPAPI round trip\x00with binary data"
        protected = protector.protect(plaintext)
        self.assertNotEqual(protected, plaintext)
        self.assertEqual(protector.unprotect(protected), plaintext)


if __name__ == "__main__":
    unittest.main()
