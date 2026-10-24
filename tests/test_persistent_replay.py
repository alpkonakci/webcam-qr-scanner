from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from bridge.protocol import (
    ReceiverCredentials, ReplayDetected, SenderCredentials,
    build_url_envelope, random_b64url,
)
from bridge.receiver import PcReceiver
from bridge.receiver_service import ReceiverGroup, ReceiverService
from bridge.replay import InMemoryReplayGuard, PersistentReplayGuard
from bridge.secure_storage import DpapiProtector, PairingStore, SecureStorageError


class TestProtector:
    """Authenticated obfuscation fixture; never production cryptography."""
    def protect(self, plaintext):
        body = bytes(byte ^ 0xA5 for byte in plaintext)
        return hmac.digest(b"replay-test-only", body, "sha256") + body

    def unprotect(self, ciphertext):
        tag, body = ciphertext[:32], ciphertext[32:]
        if not hmac.compare_digest(tag, hmac.digest(b"replay-test-only", body, "sha256")):
            raise SecureStorageError("test protection failed")
        return bytes(byte ^ 0xA5 for byte in body)


class PersistentReplayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "replay.sqlite3"
        self.now = int(time.time())
        self.message = b"m" * 16

    def guard(self, scope="https://relay.example\0pair-one"):
        return PersistentReplayGuard(self.path, scope=scope, protector=TestProtector())

    def remember(self, guard=None, now=None):
        now = self.now if now is None else now
        (guard or self.guard()).remember(self.message, expires_at=now + 300, now=now)

    def test_new_instance_rejects_an_accepted_message(self):
        self.remember()
        with self.assertRaises(ReplayDetected):
            self.remember(self.guard())

    def test_same_id_is_independent_across_pairs_and_origins(self):
        for scope in ("https://one.example\0first", "https://one.example\0second", "https://two.example\0first"):
            self.remember(self.guard(scope))
        with self.assertRaises(ReplayDetected):
            self.remember(self.guard("https://one.example\0first"))

    def test_expiry_boundary_is_retained_then_pruned(self):
        self.guard().remember(self.message, expires_at=self.now, now=self.now)
        with self.assertRaises(ReplayDetected):
            self.remember(now=self.now)
        self.remember(now=self.now + 1)

    def test_invalid_or_unbounded_entries_are_rejected_without_a_file(self):
        for message, expiry in ((b"short", self.now + 1), (self.message, self.now - 1), (self.message, self.now + 421), (self.message, True)):
            with self.assertRaises(SecureStorageError):
                self.guard().remember(message, expires_at=expiry, now=self.now)
        self.assertFalse(self.path.exists())

    def test_corrupted_protected_payload_fails_closed(self):
        self.remember()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE replay_state SET payload=?", (b"corrupted",))
        with self.assertRaises(SecureStorageError):
            self.remember()

    def test_corrupted_database_is_not_replaced(self):
        self.path.write_bytes(b"not a sqlite database")
        with self.assertRaises(SecureStorageError):
            self.remember()
        self.assertEqual(self.path.read_bytes(), b"not a sqlite database")

    def test_missing_state_row_is_not_silently_reset(self):
        self.remember()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM replay_state")
        with self.assertRaises(SecureStorageError):
            self.remember()

    def test_capacity_is_bounded_and_expired_entries_release_capacity(self):
        with patch("bridge.replay.MAX_REPLAY_RECORDS", 1):
            self.remember()
            with self.assertRaises(SecureStorageError):
                self.guard().remember(b"n" * 16, expires_at=self.now + 300, now=self.now)
            self.remember(now=self.now + 301)

    def test_transaction_serializes_concurrent_receivers(self):
        def accept(_):
            try:
                self.remember(self.guard())
                return "accepted"
            except ReplayDetected:
                return "replay"
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(accept, range(8)))
        self.assertEqual(outcomes.count("accepted"), 1)
        self.assertEqual(outcomes.count("replay"), 7)

    def test_protection_failure_never_falls_back_to_memory(self):
        protector = TestProtector()
        with patch.object(protector, "protect", side_effect=SecureStorageError("fixture failure")):
            guard = PersistentReplayGuard(self.path, scope="fixture", protector=protector)
            with self.assertRaises(SecureStorageError):
                self.remember(guard)

    def test_no_plaintext_message_id_or_scope_in_database(self):
        self.remember()
        raw = self.path.read_bytes()
        self.assertNotIn(self.message, raw)
        self.assertNotIn(b"https://relay.example", raw)
        self.assertNotIn(hashlib.sha256(self.message).hexdigest().encode(), raw)
        self.assertNotIn(b'"entries"', raw)

    def test_empty_explicit_in_memory_guard_is_preserved(self):
        guard = InMemoryReplayGuard()
        credentials = ReceiverCredentials(
            device_id=random_b64url(16), receiver_token=random_b64url(32),
            pair_id=random_b64url(16), root_key=b"r" * 32,
        )
        receiver = PcReceiver(relay_origin="https://relay.example", credentials=credentials, on_url=lambda _: None, replay_guard=guard)
        self.assertIs(receiver.replay_guard, guard)

    def test_production_service_reconnect_reuses_the_persistent_ledger(self):
        credentials = ReceiverCredentials(
            device_id=random_b64url(16), receiver_token=random_b64url(32),
            pair_id=random_b64url(16), root_key=b"r" * 32,
        )
        group = ReceiverGroup(
            relay_origin="https://relay.example", device_id=credentials.device_id,
            credentials=(credentials,), phone_labels={},
        )
        guards = []
        service = ReceiverService(
            store=PairingStore(self.path.with_name("pair.dat"), protector=TestProtector()),
        )

        def factory(**options):
            guard = options["replay_guards"][credentials.pair_id]
            guards.append(guard)

            async def run():
                if len(guards) == 1:
                    self.remember(guard)
                    raise OSError("synthetic reconnect")
                with self.assertRaises(ReplayDetected):
                    self.remember(guard)
                service.stop()

            return Mock(run=run)

        service.receiver_factory = factory
        service._interruptible_delay = AsyncMock()
        asyncio.run(service._run_group(group))
        self.assertEqual(len(guards), 2)
        self.assertIsNot(guards[0], guards[1])
        self.assertEqual(guards[0].path, guards[1].path)

    def test_storage_failure_never_acknowledges_or_opens_a_delivery(self):
        credentials = ReceiverCredentials(
            device_id=random_b64url(16), receiver_token=random_b64url(32),
            pair_id=random_b64url(16), root_key=b"r" * 32,
        )
        sender = SenderCredentials(
            pair_id=credentials.pair_id, sender_token=random_b64url(32),
            root_key=credentials.root_key,
        )
        event = {
            "event": "url_message", "delivery_id": random_b64url(16),
            "envelope": build_url_envelope(sender, "https://example.com/synthetic"),
        }
        self.path.write_bytes(b"corrupted replay database")
        callback = Mock()
        receiver = PcReceiver(
            relay_origin="https://relay.example", credentials=credentials,
            on_url=callback, replay_guards={credentials.pair_id: self.guard()},
        )
        client = Mock(get=AsyncMock(return_value=Mock(json=lambda: event)), post=AsyncMock())
        with self.assertRaises(SecureStorageError):
            asyncio.run(receiver._poll_once(client, "/synthetic"))
        client.post.assert_not_called()
        callback.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "requires current-user Windows DPAPI")
    def test_dpapi_ledger_survives_a_separate_process(self):
        scope = "https://relay.example\0separate-process"
        guard = PersistentReplayGuard(self.path, scope=scope, protector=DpapiProtector())
        self.remember(guard)
        code = (
            "import sys,time; from pathlib import Path; "
            "from bridge.replay import PersistentReplayGuard; "
            "from bridge.protocol import ReplayDetected\n"
            "try:\n"
            " PersistentReplayGuard(Path(sys.argv[1]), scope='https://relay.example\\0separate-process').remember(b'm'*16, expires_at=int(time.time())+300)\n"
            "except ReplayDetected:\n sys.exit(0)\n"
            "sys.exit(1)\n"
        )
        result = subprocess.run([sys.executable, "-c", code, str(self.path)], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
