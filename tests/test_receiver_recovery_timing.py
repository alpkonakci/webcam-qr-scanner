"""Deterministic transport timing checks; these are not live-cloud tests."""

from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import patch

import httpx

from bridge.protocol import (
    ReceiverCredentials,
    SenderCredentials,
    build_url_envelope,
    random_b64url,
)
from bridge.realtime import RealtimeConfig, RealtimeSession
from bridge.receiver import PcReceiver, _wait_for_any_event


class RecoveryTimingTests(unittest.IsolatedAsyncioTestCase):
    async def _exercise(self, transitions: tuple[bool, ...]) -> list[float]:
        credentials = ReceiverCredentials(
            device_id=random_b64url(16),
            receiver_token=random_b64url(32),
            pair_id=random_b64url(16),
            root_key=b"r" * 32,
        )
        envelope = build_url_envelope(
            SenderCredentials(
                pair_id=credentials.pair_id,
                sender_token=random_b64url(32),
                root_key=credentials.root_key,
            ),
            "https://example.com/recovery-audit",
        )
        event = {
            "event": "url_message",
            "delivery_id": random_b64url(16),
            "envelope": envelope,
        }
        state = {"ready": False, "cancelled": False, "posts": 0}
        realtime_clients = []

        class ControlledRealtime:
            def __init__(self, **kwargs):
                self.connected = asyncio.Event()
                self.changed = kwargs["on_connection_change"]
                self.wakeup = kwargs["on_wakeup"]
                if transitions[0]:
                    self.connected.set()
                realtime_clients.append(self)

            async def run(self):
                try:
                    await asyncio.Event().wait()
                finally:
                    state["cancelled"] = True

        class ControlledHttp:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def get(self, path):
                # Allow the real receiver's background task to start.
                await asyncio.sleep(0)
                request = httpx.Request("GET", f"https://relay.example{path}")
                return (
                    httpx.Response(200, request=request, json=event)
                    if state["ready"]
                    else httpx.Response(204, request=request)
                )

            async def post(self, path, *, json):
                self_test.assertEqual(json["event"], "delivery_ack")
                state["posts"] += 1
                return httpx.Response(
                    202, request=httpx.Request("POST", f"https://relay.example{path}")
                )

        self_test = self
        waits = []

        async def controlled_wait(events, *, timeout):
            waits.append(timeout)
            index = len(waits)
            client = realtime_clients[0]
            if index < len(transitions):
                next_connected = transitions[index]
                if next_connected:
                    client.connected.set()
                else:
                    client.connected.clear()
                client.changed(next_connected)
                self.assertTrue(events[1].is_set())
            else:
                state["ready"] = True

        session = RealtimeSession(
            access_token="a" * 80,
            refresh_token="r" * 48,
            expires_at=int(time.time()) + 3600,
            user_id="3f25129c-8558-4bdf-a37d-e70b650e25b1",
        )
        received = []
        receiver = PcReceiver(
            relay_origin="https://relay.example",
            credentials=credentials,
            realtime_session=session,
            on_url=received.append,
        )
        config = RealtimeConfig(
            supabase_url="https://example.supabase.co",
            publishable_key="sb_publishable_" + "p" * 32,
        )
        with (
            patch("bridge.receiver.fetch_realtime_config", return_value=config),
            patch("bridge.receiver.RealtimeWakeupClient", ControlledRealtime),
            patch("bridge.receiver.httpx.AsyncClient", return_value=ControlledHttp()),
            patch("bridge.receiver._wait_for_any_event", controlled_wait),
        ):
            await asyncio.wait_for(receiver.run(stop_after=1), timeout=2)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].url, "https://example.com/recovery-audit")
        self.assertEqual(state["posts"], 1)
        self.assertTrue(state["cancelled"])
        return waits

    async def test_healthy_channel_selects_sixty_second_safety_resync(self):
        self.assertEqual(await self._exercise((True,)), [60.0])

    async def test_disconnected_channel_selects_five_second_fallback(self):
        self.assertEqual(await self._exercise((False,)), [5.0])

    async def test_disconnect_interrupts_resync_and_changes_to_fallback(self):
        self.assertEqual(await self._exercise((True, False)), [60.0, 5.0])

    async def test_reconnect_changes_back_to_sixty_second_safety_resync(self):
        self.assertEqual(await self._exercise((False, True)), [5.0, 60.0])

    async def test_wakeup_interrupts_real_long_wait_and_cleans_up_tasks(self):
        wakeup, changed = asyncio.Event(), asyncio.Event()
        before = set(asyncio.all_tasks())
        task = asyncio.create_task(_wait_for_any_event((wakeup, changed), timeout=60))
        await asyncio.sleep(0)
        wakeup.set()
        await asyncio.wait_for(task, timeout=1)
        self.assertEqual(set(asyncio.all_tasks()), before)

    async def test_cancelled_wait_cleans_up_event_waiters(self):
        before = set(asyncio.all_tasks())
        task = asyncio.create_task(
            _wait_for_any_event((asyncio.Event(), asyncio.Event()), timeout=60)
        )
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(set(asyncio.all_tasks()), before)


if __name__ == "__main__":
    unittest.main()
