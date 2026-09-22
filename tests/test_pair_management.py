from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from bridge.pair_management import (
    PairManagementService,
    PairRemovalStatus,
)
from bridge.pairing import (
    PairRevocationError,
    RemotePairRevocationStatus,
    revoke_remote_pair,
)
from bridge.protocol import random_b64url
from bridge.secure_storage import PairingStore, RelayDevice, StoredPair


class XorTestProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return bytes(value ^ 0x5A for value in plaintext)

    def unprotect(self, ciphertext: bytes) -> bytes:
        return bytes(value ^ 0x5A for value in ciphertext)


class PairManagementServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = PairingStore(
            Path(self.directory.name) / "phone-to-pc.dat",
            protector=XorTestProtector(),
        )
        self.device = RelayDevice(
            relay_origin="https://relay.example",
            device_id=random_b64url(16),
            receiver_token=random_b64url(32),
        )
        self.pair = StoredPair(
            relay_origin=self.device.relay_origin,
            device_id=self.device.device_id,
            pair_id=random_b64url(16),
            root_key=os.urandom(32),
            phone_label="My iPhone",
        )
        self.store.replace_device(self.device, clear_pairs=False)
        self.store.add_pair(self.pair)
        self.service = PairManagementService(store=self.store)

    def test_list_pairs_exposes_only_display_safe_fields(self) -> None:
        summaries = self.service.list_pairs()

        self.assertEqual(len(summaries), 1)
        summary = summaries[0]
        self.assertEqual(summary.relay_origin, self.pair.relay_origin)
        self.assertEqual(summary.pair_id, self.pair.pair_id)
        self.assertEqual(summary.phone_label, self.pair.phone_label)
        self.assertEqual(
            summary.short_pair_id,
            f"{self.pair.pair_id[:6]}\N{HORIZONTAL ELLIPSIS}"
            f"{self.pair.pair_id[-4:]}",
        )
        self.assertFalse(hasattr(summary, "root_key"))
        self.assertFalse(hasattr(summary, "receiver_token"))

    async def test_remote_success_precedes_local_removal(self) -> None:
        remote = AsyncMock(
            return_value=RemotePairRevocationStatus.REVOKED
        )
        with patch(
            "bridge.pair_management.revoke_remote_pair",
            new=remote,
        ):
            result = await self.service.remove_pair_async(
                relay_origin=self.pair.relay_origin,
                pair_id=self.pair.pair_id,
            )

        self.assertEqual(result.status, PairRemovalStatus.REVOKED)
        self.assertEqual(self.store.load().pairs, ())
        self.assertEqual(self.store.load().devices, (self.device,))
        remote.assert_awaited_once_with(
            relay_origin=self.pair.relay_origin,
            pair_id=self.pair.pair_id,
            receiver_token=self.device.receiver_token,
        )

    async def test_network_failure_preserves_local_credentials(self) -> None:
        with patch(
            "bridge.pair_management.revoke_remote_pair",
            new=AsyncMock(
                side_effect=PairRevocationError(code="network_error")
            ),
        ):
            with self.assertRaises(PairRevocationError):
                await self.service.remove_pair_async(
                    relay_origin=self.pair.relay_origin,
                    pair_id=self.pair.pair_id,
                )

        self.assertEqual(self.store.load().pairs, (self.pair,))
        self.assertEqual(self.store.load().devices, (self.device,))

    async def test_remote_not_found_allows_local_cleanup(self) -> None:
        with patch(
            "bridge.pair_management.revoke_remote_pair",
            new=AsyncMock(
                return_value=RemotePairRevocationStatus.ALREADY_REVOKED
            ),
        ):
            result = await self.service.remove_pair_async(
                relay_origin=self.pair.relay_origin,
                pair_id=self.pair.pair_id,
            )

        self.assertEqual(
            result.status,
            PairRemovalStatus.ALREADY_REVOKED,
        )
        self.assertEqual(self.store.load().pairs, ())

    async def test_synchronous_adapter_is_safe_for_desktop_callbacks(
        self,
    ) -> None:
        with patch(
            "bridge.pair_management.revoke_remote_pair",
            new=AsyncMock(
                return_value=RemotePairRevocationStatus.REVOKED
            ),
        ):
            result = await asyncio.to_thread(
                self.service.remove_pair,
                relay_origin=self.pair.relay_origin,
                pair_id=self.pair.pair_id,
            )

        self.assertEqual(result.status, PairRemovalStatus.REVOKED)
        self.assertEqual(self.store.load().pairs, ())


class RemotePairRevocationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.origin = "https://relay.example"
        self.pair_id = random_b64url(16)
        self.receiver_token = random_b64url(32)

    async def test_success_response_is_validated(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "DELETE")
            self.assertEqual(request.url.path, f"/v1/pairs/{self.pair_id}")
            self.assertEqual(
                request.headers["Authorization"],
                f"Bearer {self.receiver_token}",
            )
            return httpx.Response(
                200,
                json={"status": "revoked", "pair_id": self.pair_id},
            )

        status = await self._call_with_handler(handler)
        self.assertIs(status, RemotePairRevocationStatus.REVOKED)

    async def test_local_relay_pair_not_found_is_idempotent_success(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                404,
                json={
                    "error": {
                        "code": "pair_not_found",
                        "message": "Pair was not found.",
                    }
                },
            )

        status = await self._call_with_handler(handler)
        self.assertIs(
            status,
            RemotePairRevocationStatus.ALREADY_REVOKED,
        )

    async def test_server_failure_raises_retryable_error(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                503,
                json={
                    "error": {
                        "code": "relay_unavailable",
                        "message": "Try again later.",
                    }
                },
            )

        with self.assertRaises(PairRevocationError) as raised:
            await self._call_with_handler(handler)

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.code, "relay_unavailable")
        self.assertTrue(raised.exception.retryable)

    async def test_network_failure_does_not_expose_credentials(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection failed", request=request)

        with self.assertRaises(PairRevocationError) as raised:
            await self._call_with_handler(handler)

        self.assertEqual(raised.exception.code, "network_error")
        self.assertIsNone(raised.exception.status_code)
        self.assertTrue(raised.exception.retryable)
        message = str(raised.exception)
        self.assertNotIn(self.origin, message)
        self.assertNotIn(self.pair_id, message)
        self.assertNotIn(self.receiver_token, message)

    async def _call_with_handler(
        self,
        handler: Callable[[httpx.Request], httpx.Response],
    ) -> RemotePairRevocationStatus:
        client = httpx.AsyncClient(
            base_url=self.origin,
            transport=httpx.MockTransport(handler),
        )
        with patch("bridge.pairing._client", return_value=client):
            return await revoke_remote_pair(
                relay_origin=self.origin,
                pair_id=self.pair_id,
                receiver_token=self.receiver_token,
            )


if __name__ == "__main__":
    unittest.main()
