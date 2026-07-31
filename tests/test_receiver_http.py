from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from bridge.protocol import (
    ReceiverCredentials,
    SenderCredentials,
    build_url_envelope,
    random_b64url,
)
from bridge.receiver import PcReceiver


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

        with patch("bridge.receiver.httpx.AsyncClient", return_value=client):
            await receiver.run(stop_after=1)

        self.assertTrue(receiver.connected.is_set())
        self.assertEqual(received[0].pair_id, second.pair_id)
        self.assertEqual(received[0].url, "https://example.com/from-phone")
        self.assertEqual(len(client.posts), 1)
        self.assertEqual(client.posts[0][1]["event"], "delivery_ack")
        self.assertEqual(client.posts[0][1]["delivery_id"], delivery_id)


if __name__ == "__main__":
    unittest.main()
