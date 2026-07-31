from __future__ import annotations

import asyncio
import contextlib
import copy
import socket
import unittest

import httpx
import uvicorn

from bridge.fake_phone import DeliveryFailed, FakePhone
from bridge.pairing import (
    complete_pc_pairing,
    open_pc_pairing,
    submit_phone_pairing_request,
    wait_for_pc_result,
    wait_for_phone_request,
)
from bridge.protocol import (
    PROTOCOL,
    build_url_envelope,
    create_phone_pairing_attempt,
    random_b64url,
)
from bridge.provision import provision_local_pairing
from bridge.receiver import PcReceiver
from relay.app import create_app
from relay.state import PairingStateError, RelayState


class LiveRelay:
    def __init__(self) -> None:
        self.port = self._available_port()
        self.origin = f"http://127.0.0.1:{self.port}"
        self.application = create_app()
        self.server = uvicorn.Server(
            uvicorn.Config(
                self.application,
                host="127.0.0.1",
                port=self.port,
                access_log=False,
                log_level="warning",
                lifespan="off",
            )
        )
        self.task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> LiveRelay:
        self.task = asyncio.create_task(self.server.serve())
        for _ in range(250):
            if self.server.started:
                return self
            if self.task.done():
                await self.task
                raise RuntimeError("relay ended before startup")
            await asyncio.sleep(0.02)
        raise TimeoutError("relay did not start")

    async def __aexit__(self, *_: object) -> None:
        self.server.should_exit = True
        if self.task is not None:
            await asyncio.wait_for(self.task, timeout=5)

    @staticmethod
    def _available_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])


class RelayStateTests(unittest.TestCase):
    def test_state_keeps_only_token_digests_and_safe_routing_metadata(self) -> None:
        state = RelayState(token_pepper=b"p" * 32)
        device_id, receiver_token = state.create_device()
        sender_token = random_b64url(32)
        pair_id = random_b64url(16)
        state.register_pair(
            device_id=device_id,
            pair_id=pair_id,
            sender_token=sender_token,
        )
        raw_state = repr(vars(state))
        self.assertNotIn(receiver_token, raw_state)
        self.assertNotIn(sender_token, raw_state)
        self.assertEqual(
            state.safe_snapshot(),
            {
                "device_count": 1,
                "pair_count": 1,
                "pairing_count": 0,
                "connected_device_count": 0,
                "device_ids": [device_id],
                "pair_ids": [pair_id],
                "pairing_ids": [],
            },
        )

    def test_pairing_route_is_short_lived_single_use_and_token_hashed(
        self,
    ) -> None:
        state = RelayState(token_pepper=b"p" * 32)
        device_id, _ = state.create_device()
        pairing_id, pairing_token, expires_at = state.create_pairing(
            device_id=device_id,
            now=1_000,
        )
        envelope = {
            "device_id": device_id,
            "pairing_id": pairing_id,
            "expires_at": expires_at,
        }

        state.submit_pairing_request(
            pairing_id=pairing_id,
            pairing_token=pairing_token,
            envelope=envelope,
            now=1_000,
        )
        with self.assertRaises(PairingStateError) as repeated:
            state.submit_pairing_request(
                pairing_id=pairing_id,
                pairing_token=pairing_token,
                envelope=envelope,
                now=1_000,
            )
        self.assertEqual(repeated.exception.code, "pairing_already_used")
        with self.assertRaises(PairingStateError) as expired:
            state.pairing_result_for_phone(
                pairing_id=pairing_id,
                pairing_token=pairing_token,
                now=expires_at + 1,
            )
        self.assertEqual(expired.exception.code, "pairing_expired")
        self.assertNotIn(pairing_token, repr(vars(state)))


class LocalRelayEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_secure_persistence_revokes_approved_route(
        self,
    ) -> None:
        async with LiveRelay() as live:
            async with httpx.AsyncClient(
                base_url=live.origin,
                timeout=5,
            ) as client:
                device_response = await client.post("/v1/devices")
            device = device_response.json()
            session = await open_pc_pairing(
                relay_origin=live.origin,
                device_id=device["device_id"],
                receiver_token=device["receiver_token"],
            )
            phone = create_phone_pairing_attempt(
                session.pairing_uri,
                phone_label="Storage failure phone",
            )
            await submit_phone_pairing_request(phone)
            request = await wait_for_phone_request(
                session,
                timeout_seconds=5,
            )

            def fail_persistence(_):
                raise OSError("simulated secure storage failure")

            with self.assertRaises(OSError):
                await complete_pc_pairing(
                    session,
                    request,
                    approved=True,
                    pc_label="Test PC",
                    persist_receiver=fail_persistence,
                )

            self.assertEqual(
                live.application.state.relay.safe_snapshot()["pair_count"],
                0,
            )
            async with httpx.AsyncClient(
                base_url=live.origin,
                timeout=5,
            ) as client:
                result_response = await client.get(
                    f"/v1/pairings/{session.qr.pairing_id}/result",
                    headers={
                        "Authorization": (
                            f"Bearer {session.qr.pairing_token}"
                        )
                    },
                )
            self.assertEqual(result_response.status_code, 202)

    async def test_rejected_phone_request_creates_no_pair_route(self) -> None:
        async with LiveRelay() as live:
            async with httpx.AsyncClient(
                base_url=live.origin,
                timeout=5,
            ) as client:
                device_response = await client.post("/v1/devices")
            device = device_response.json()
            session = await open_pc_pairing(
                relay_origin=live.origin,
                device_id=device["device_id"],
                receiver_token=device["receiver_token"],
            )
            phone = create_phone_pairing_attempt(
                session.pairing_uri,
                phone_label="Rejected phone",
            )
            await submit_phone_pairing_request(phone)
            request = await wait_for_phone_request(
                session,
                timeout_seconds=5,
            )
            decision = await complete_pc_pairing(
                session,
                request,
                approved=False,
                pc_label="Test PC",
            )
            sender = await wait_for_pc_result(phone, timeout_seconds=5)

            self.assertFalse(decision.approved)
            self.assertIsNone(decision.receiver)
            self.assertIsNone(sender)
            self.assertEqual(
                live.application.state.relay.safe_snapshot()["pair_count"],
                0,
            )

    async def test_encrypted_delivery_opens_pc_callback_without_relay_url_data(
        self,
    ) -> None:
        clear_url = "https://example.com/private-path?token=not-for-relay"
        received_urls: list[str] = []
        async with LiveRelay() as live:
            pairing = await provision_local_pairing(live.origin)
            receiver = PcReceiver(
                relay_origin=live.origin,
                credentials=pairing.receiver,
                on_url=lambda received: received_urls.append(received.url),
            )
            receiver_task = asyncio.create_task(receiver.run(stop_after=1))
            await asyncio.wait_for(receiver.connected.wait(), timeout=5)

            result = await FakePhone(
                relay_origin=live.origin,
                credentials=pairing.sender,
            ).send_url(clear_url)
            await asyncio.wait_for(receiver_task, timeout=5)

            self.assertEqual(result.status, "delivered")
            self.assertEqual(received_urls, [clear_url])
            self.assertNotIn(
                clear_url,
                repr(live.application.state.relay.safe_snapshot()),
            )
            self.assertNotIn(
                clear_url,
                repr(vars(live.application.state.relay)),
            )

    async def test_replay_is_rejected_after_first_delivery(self) -> None:
        async with LiveRelay() as live:
            pairing = await provision_local_pairing(live.origin)
            received_urls: list[str] = []
            receiver = PcReceiver(
                relay_origin=live.origin,
                credentials=pairing.receiver,
                on_url=lambda received: received_urls.append(received.url),
            )
            receiver_task = asyncio.create_task(receiver.run())
            await asyncio.wait_for(receiver.connected.wait(), timeout=5)
            phone = FakePhone(
                relay_origin=live.origin,
                credentials=pairing.sender,
            )
            envelope = build_url_envelope(
                pairing.sender,
                "https://example.com/once",
            )

            await phone.send_envelope(envelope)
            with self.assertRaises(DeliveryFailed) as context:
                await phone.send_envelope(envelope)
            self.assertEqual(context.exception.code, "delivery_rejected")
            self.assertEqual(received_urls, ["https://example.com/once"])
            await self._cancel(receiver_task)

    async def test_tamper_is_rejected_but_original_message_remains_usable(
        self,
    ) -> None:
        async with LiveRelay() as live:
            pairing = await provision_local_pairing(live.origin)
            received_urls: list[str] = []
            receiver = PcReceiver(
                relay_origin=live.origin,
                credentials=pairing.receiver,
                on_url=lambda received: received_urls.append(received.url),
            )
            receiver_task = asyncio.create_task(receiver.run(stop_after=1))
            await asyncio.wait_for(receiver.connected.wait(), timeout=5)
            phone = FakePhone(
                relay_origin=live.origin,
                credentials=pairing.sender,
            )
            envelope = build_url_envelope(
                pairing.sender,
                "https://example.com/authenticated",
            )
            tampered = copy.deepcopy(envelope)
            replacement = "A" if tampered["ciphertext"][0] != "A" else "B"
            tampered["ciphertext"] = replacement + tampered["ciphertext"][1:]

            with self.assertRaises(DeliveryFailed):
                await phone.send_envelope(tampered)
            result = await phone.send_envelope(envelope)
            await asyncio.wait_for(receiver_task, timeout=5)
            self.assertEqual(result.status, "delivered")
            self.assertEqual(received_urls, ["https://example.com/authenticated"])

    async def test_offline_and_revoked_pair_fail_closed(self) -> None:
        async with LiveRelay() as live:
            pairing = await provision_local_pairing(live.origin)
            phone = FakePhone(
                relay_origin=live.origin,
                credentials=pairing.sender,
            )
            with self.assertRaises(DeliveryFailed) as offline:
                await phone.send_url("https://example.com/offline")
            self.assertEqual(offline.exception.code, "receiver_offline")

            async with httpx.AsyncClient(
                base_url=live.origin,
                timeout=5,
            ) as client:
                response = await client.delete(
                    f"/v1/pairs/{pairing.receiver.pair_id}",
                    headers={
                        "Authorization": (
                            f"Bearer {pairing.receiver.receiver_token}"
                        )
                    },
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "revoked")

            with self.assertRaises(DeliveryFailed) as revoked:
                await phone.send_url("https://example.com/revoked")
            self.assertEqual(revoked.exception.code, "unauthorized")

    async def test_health_endpoint_discloses_no_state(self) -> None:
        async with LiveRelay() as live:
            async with httpx.AsyncClient(
                base_url=live.origin,
                timeout=5,
            ) as client:
                response = await client.get("/healthz")
            self.assertEqual(
                response.json(),
                {"status": "ok", "protocol": PROTOCOL},
            )

    async def test_plaintext_or_wrong_shape_is_not_routed(self) -> None:
        async with LiveRelay() as live:
            pairing = await provision_local_pairing(live.origin)
            async with httpx.AsyncClient(
                base_url=live.origin,
                timeout=5,
            ) as client:
                response = await client.post(
                    f"/v1/pairs/{pairing.sender.pair_id}/messages",
                    headers={
                        "Authorization": (
                            f"Bearer {pairing.sender.sender_token}"
                        )
                    },
                    json={"url": "https://example.com/plaintext"},
                )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(
                response.json()["error"]["code"],
                "invalid_request",
            )

    @staticmethod
    async def _cancel(task: asyncio.Task[None]) -> None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


if __name__ == "__main__":
    unittest.main()
