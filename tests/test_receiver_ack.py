"""ACK transport failures must not discard an authenticated local receipt."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import httpx

from bridge.protocol import (
    ReceiverCredentials, SenderCredentials, build_url_envelope, random_b64url,
)
from bridge.receiver import PcReceiver


class ReceiverAckTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.credentials = ReceiverCredentials(
            device_id=random_b64url(16), receiver_token=random_b64url(32),
            pair_id=random_b64url(16), root_key=b"a" * 32,
        )
        self.event = {
            "event": "url_message", "delivery_id": random_b64url(16),
            "envelope": build_url_envelope(SenderCredentials(
                pair_id=self.credentials.pair_id, sender_token=random_b64url(32),
                root_key=self.credentials.root_key,
            ), "https://example.com/ack-loss"),
        }
        self.received = []

    def receiver(self, origin="https://relay.example"):
        return PcReceiver(relay_origin=origin, credentials=self.credentials,
                          on_url=self.received.append)

    async def test_explicit_ack_rejection_does_not_prompt(self):
        for status in (401, 403, 404, 503):
            with self.subTest(status=status):
                def transport(request):
                    return (httpx.Response(200, json=self.event)
                            if request.method == "GET" else httpx.Response(status))

                async with httpx.AsyncClient(
                    base_url="https://relay.example",
                    transport=httpx.MockTransport(transport),
                ) as client:
                    with self.assertRaises(httpx.HTTPStatusError):
                        await self.receiver()._poll_once(client, "/messages")
                self.assertEqual(self.received, [])

    async def test_websocket_ack_send_failure_still_prompts_once(self):
        event = self.event

        class Socket:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            def __aiter__(self):
                async def messages():
                    yield json.dumps(event)
                return messages()

            async def send(self, message):
                if json.loads(message)["event"] == "delivery_ack":
                    raise OSError("synthetic WebSocket ACK loss")

        receiver = self.receiver("http://127.0.0.1:8765")
        with patch("bridge.receiver.connect", return_value=Socket()):
            with self.assertRaises(OSError):
                await receiver.run()
            self.assertEqual([item.url for item in self.received],
                             ["https://example.com/ack-loss"])
            # Replayed input is rejected before a second confirmation callback.
            await receiver.run()
            self.assertEqual(len(self.received), 1)


if __name__ == "__main__":
    unittest.main()
