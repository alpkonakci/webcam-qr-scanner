from __future__ import annotations

import unittest
import time
from unittest.mock import patch

import httpx

from bridge.protocol import (
    ReceiverCredentials,
    SenderCredentials,
    build_url_envelope,
    random_b64url,
)
from bridge.receiver import PcReceiver
from bridge.realtime import RealtimeConfig, RealtimeSession


class _FakeHttpClient:
    def __init__(self, event: dict[str, object]) -> None:
        self.event = event
        self.posts: list[tuple[str, dict[str, object]]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def get(self, path: str) -> httpx.Response:
        return httpx.Response(
            200,
            json=self.event,
            request=httpx.Request("GET", f"https://relay.example{path}"),
        )

    async def post(
        self,
        path: str,
        *,
        json: dict[str, object],
    ) -> httpx.Response:
        self.posts.append((path, json))
        return httpx.Response(
            202,
            json={"status": "delivered"},
            request=httpx.Request("POST", f"https://relay.example{path}"),
        )


class _FallbackHttpClient(_FakeHttpClient):
    def __init__(self, event: dict[str, object]) -> None:
        super().__init__(event)
        self.get_count = 0

    async def get(self, path: str) -> httpx.Response:
        self.get_count += 1
        if self.get_count == 1:
            return httpx.Response(
                204,
                request=httpx.Request(
                    "GET",
                    f"https://relay.example{path}",
                ),
            )
        return await super().get(path)


class _IdleRealtimeClient:
    def __init__(self, **_):
        import asyncio

        self.connected = asyncio.Event()

    async def run(self) -> None:
        import asyncio

        await asyncio.Event().wait()


class HttpReceiverTests(unittest.IsolatedAsyncioTestCase):
    async def test_https_receiver_polls_and_acknowledges_matching_pair(
        self,
    ) -> None:
        device_id = random_b64url(16)
        receiver_token = random_b64url(32)
        first_root = b"a" * 32
        second_root = b"b" * 32
        first = ReceiverCredentials(
            device_id=device_id,
            receiver_token=receiver_token,
            pair_id=random_b64url(16),
            root_key=first_root,
        )
        second = ReceiverCredentials(
            device_id=device_id,
            receiver_token=receiver_token,
            pair_id=random_b64url(16),
            root_key=second_root,
        )
        envelope = build_url_envelope(
            SenderCredentials(
                pair_id=second.pair_id,
                sender_token=random_b64url(32),
                root_key=second_root,
            ),
            "https://example.com/from-phone",
        )
        delivery_id = random_b64url(16)
        client = _FakeHttpClient(
            {
                "event": "url_message",
                "delivery_id": delivery_id,
                "envelope": envelope,
            }
        )
        received = []
        receiver = PcReceiver(
            relay_origin="https://relay.example",
            credentials=(first, second),
            on_url=received.append,
        )

        with (
            patch("bridge.receiver.fetch_realtime_config", return_value=None),
            patch("bridge.receiver.httpx.AsyncClient", return_value=client),
        ):
            await receiver.run(stop_after=1)

        self.assertTrue(receiver.connected.is_set())
        self.assertEqual(received[0].pair_id, second.pair_id)
        self.assertEqual(received[0].url, "https://example.com/from-phone")
        self.assertEqual(len(client.posts), 1)
        self.assertEqual(client.posts[0][1]["event"], "delivery_ack")
        self.assertEqual(client.posts[0][1]["delivery_id"], delivery_id)

    async def test_realtime_transport_keeps_five_second_recovery_poll(
        self,
    ) -> None:
        device_id = random_b64url(16)
        root_key = b"r" * 32
        credentials = ReceiverCredentials(
            device_id=device_id,
            receiver_token=random_b64url(32),
            pair_id=random_b64url(16),
            root_key=root_key,
        )
        envelope = build_url_envelope(
            SenderCredentials(
                pair_id=credentials.pair_id,
                sender_token=random_b64url(32),
                root_key=root_key,
            ),
            "https://example.com/recovered",
        )
        client = _FallbackHttpClient(
            {
                "event": "url_message",
                "delivery_id": random_b64url(16),
                "envelope": envelope,
            }
        )
        session = RealtimeSession(
            access_token="a" * 80,
            refresh_token="r" * 48,
            expires_at=int(time.time()) + 3600,
            user_id="3f25129c-8558-4bdf-a37d-e70b650e25b1",
        )
        receiver = PcReceiver(
            relay_origin="https://relay.example",
            credentials=credentials,
            on_url=lambda _: None,
            realtime_session=session,
        )
        config = RealtimeConfig(
            supabase_url="https://project.supabase.co",
            publishable_key="sb_publishable_" + "p" * 32,
            # Keep the unit test fast; production config is fixed at 5 seconds.
            fallback_poll_seconds=0.01,
        )

        with (
            patch(
                "bridge.receiver.fetch_realtime_config",
                return_value=config,
            ),
            patch(
                "bridge.receiver.RealtimeWakeupClient",
                _IdleRealtimeClient,
            ),
            patch("bridge.receiver.httpx.AsyncClient", return_value=client),
        ):
            await receiver.run(stop_after=1)

        self.assertEqual(client.get_count, 2)
        self.assertEqual(len(client.posts), 1)


if __name__ == "__main__":
    unittest.main()
