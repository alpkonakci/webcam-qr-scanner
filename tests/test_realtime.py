from __future__ import annotations

import time
import unittest
from unittest.mock import patch

import httpx

from bridge.realtime import (
    RealtimeConfig,
    RealtimeSession,
    RealtimeTransportError,
    _is_delivery_wakeup,
    _realtime_websocket_url,
    create_anonymous_session,
    fetch_realtime_config,
    refresh_session,
)


PUBLISHABLE_KEY = "sb_publishable_" + "p" * 32
USER_ID = "3f25129c-8558-4bdf-a37d-e70b650e25b1"


class _FakeAuthClient:
    def __init__(self, responses: dict[tuple[str, str], httpx.Response]) -> None:
        self.responses = responses
        self.posts: list[tuple[str, object, dict[str, str] | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def get(self, path: str) -> httpx.Response:
        return self.responses[("GET", path)]

    async def post(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json: object = None,
    ) -> httpx.Response:
        self.posts.append((path, json, headers))
        return self.responses[("POST", path)]


def _response(method: str, url: str, body: object, status: int = 200):
    return httpx.Response(
        status,
        json=body,
        request=httpx.Request(method, url),
    )


def _session_body(*, user_id: str = USER_ID) -> dict[str, object]:
    return {
        "access_token": "a" * 80,
        "refresh_token": "r" * 48,
        "expires_at": int(time.time()) + 3600,
        "expires_in": 3600,
        "user": {"id": user_id},
    }


class RealtimeTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_only_public_realtime_configuration(self) -> None:
        value = {
            "protocol": "wqrs/1",
            "url": "https://project.supabase.co",
            "publishableKey": PUBLISHABLE_KEY,
            "fallback_poll_seconds": 5,
            "connected_resync_seconds": 60,
        }
        client = _FakeAuthClient(
            {
                ("GET", "/v1/realtime/config"): _response(
                    "GET",
                    "https://relay.example/v1/realtime/config",
                    value,
                )
            }
        )

        with patch("bridge.realtime.httpx.AsyncClient", return_value=client):
            config = await fetch_realtime_config("https://relay.example")

        self.assertEqual(
            config,
            RealtimeConfig(
                supabase_url="https://project.supabase.co",
                publishable_key=PUBLISHABLE_KEY,
                fallback_poll_seconds=5.0,
                connected_resync_seconds=60.0,
            ),
        )

    async def test_legacy_relay_without_config_remains_supported(self) -> None:
        client = _FakeAuthClient(
            {
                ("GET", "/v1/realtime/config"): _response(
                    "GET",
                    "https://relay.example/v1/realtime/config",
                    {"error": "not found"},
                    status=404,
                )
            }
        )

        with patch("bridge.realtime.httpx.AsyncClient", return_value=client):
            self.assertIsNone(
                await fetch_realtime_config("https://relay.example")
            )

    async def test_anonymous_session_sends_no_email_phone_or_profile(self) -> None:
        config = RealtimeConfig(
            supabase_url="https://project.supabase.co",
            publishable_key=PUBLISHABLE_KEY,
        )
        path = "/auth/v1/signup"
        client = _FakeAuthClient(
            {
                ("POST", path): _response(
                    "POST",
                    f"{config.supabase_url}{path}",
                    _session_body(),
                )
            }
        )

        with patch("bridge.realtime.httpx.AsyncClient", return_value=client):
            session = await create_anonymous_session(config)

        self.assertEqual(session.user_id, USER_ID)
        self.assertEqual(client.posts[0][1], {})
        self.assertEqual(client.posts[0][2]["apikey"], PUBLISHABLE_KEY)

    async def test_refresh_fails_closed_if_identity_changes(self) -> None:
        config = RealtimeConfig(
            supabase_url="https://project.supabase.co",
            publishable_key=PUBLISHABLE_KEY,
        )
        session = RealtimeSession(
            access_token="a" * 80,
            refresh_token="r" * 48,
            expires_at=int(time.time()) - 1,
            user_id=USER_ID,
        )
        path = "/auth/v1/token?grant_type=refresh_token"
        client = _FakeAuthClient(
            {
                ("POST", path): _response(
                    "POST",
                    f"{config.supabase_url}{path}",
                    _session_body(
                        user_id="e5af8b2c-b494-43b7-8444-2fa09e708c4f"
                    ),
                )
            }
        )

        with (
            patch("bridge.realtime.httpx.AsyncClient", return_value=client),
            self.assertRaises(RealtimeTransportError),
        ):
            await refresh_session(config, session)

    def test_private_channel_url_and_wakeup_shape_are_bounded(self) -> None:
        config = RealtimeConfig(
            supabase_url="https://project.supabase.co",
            publishable_key=PUBLISHABLE_KEY,
        )
        websocket_url = _realtime_websocket_url(config)
        self.assertTrue(websocket_url.startswith("wss://project.supabase.co/"))
        self.assertIn("vsn=2.0.0", websocket_url)
        self.assertTrue(
            _is_delivery_wakeup(
                {
                    "event": "delivery_ready",
                    "payload": {"delivery_id": "A" * 22},
                }
            )
        )
        self.assertFalse(
            _is_delivery_wakeup(
                {
                    "event": "delivery_ready",
                    "payload": {"delivery_id": "../../unsafe"},
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
