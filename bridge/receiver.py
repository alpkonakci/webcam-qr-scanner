"""PC-side WebSocket receiver for encrypted Phone-to-PC messages."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from websockets.asyncio.client import connect

from bridge.protocol import (
    ProtocolViolation,
    ReceivedUrl,
    ReceiverCredentials,
    build_delivery_ack,
    decrypt_url_envelope,
    normalize_relay_origin,
)
from bridge.replay import InMemoryReplayGuard


UrlCallback = Callable[[ReceivedUrl], None | Awaitable[None]]


class PcReceiver:
    """Maintain the PC relay connection and fail closed on bad messages."""

    def __init__(
        self,
        *,
        relay_origin: str,
        credentials: ReceiverCredentials,
        on_url: UrlCallback,
        replay_guard: InMemoryReplayGuard | None = None,
    ) -> None:
        self.relay_origin = normalize_relay_origin(relay_origin)
        self.credentials = credentials
        self.on_url = on_url
        self.replay_guard = replay_guard or InMemoryReplayGuard()
        self.connected = asyncio.Event()

    async def run(self, *, stop_after: int | None = None) -> None:
        """Receive until cancelled or until ``stop_after`` valid URLs."""

        websocket_url = _websocket_url(
            self.relay_origin,
            f"/v1/devices/{self.credentials.device_id}/connect",
        )
        delivered = 0
        async with connect(
            websocket_url,
            additional_headers={
                "Authorization": f"Bearer {self.credentials.receiver_token}"
            },
            max_size=16 * 1024,
            open_timeout=5,
            close_timeout=2,
        ) as websocket:
            self.connected.set()
            async for raw_message in websocket:
                try:
                    event = _parse_delivery_event(raw_message)
                    received = decrypt_url_envelope(
                        self.credentials,
                        event["envelope"],
                        replay_guard=self.replay_guard,
                    )
                    acknowledgement = build_delivery_ack(
                        self.credentials,
                        received.message_id,
                    )
                except (ProtocolViolation, ValueError, json.JSONDecodeError):
                    delivery_id = _best_effort_delivery_id(raw_message)
                    if delivery_id is not None:
                        await websocket.send(
                            json.dumps(
                                {
                                    "event": "delivery_error",
                                    "delivery_id": delivery_id,
                                },
                                separators=(",", ":"),
                            )
                        )
                    continue

                await websocket.send(
                    json.dumps(
                        {
                            "event": "delivery_ack",
                            "delivery_id": event["delivery_id"],
                            "envelope": acknowledgement,
                        },
                        separators=(",", ":"),
                    )
                )
                await _run_callback(self.on_url, received)
                delivered += 1
                if stop_after is not None and delivered >= stop_after:
                    return


def _websocket_url(origin: str, path: str) -> str:
    parsed = urlsplit(origin)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunsplit((scheme, parsed.netloc, path, "", ""))


def _parse_delivery_event(raw_message: object) -> dict[str, Any]:
    if not isinstance(raw_message, str):
        raise ProtocolViolation("relay event must be text JSON")
    value = json.loads(raw_message)
    if (
        not isinstance(value, dict)
        or set(value) != {"event", "delivery_id", "envelope"}
        or value["event"] != "url_message"
        or not isinstance(value["delivery_id"], str)
        or not isinstance(value["envelope"], dict)
    ):
        raise ProtocolViolation("relay delivery event is invalid")
    return value


def _best_effort_delivery_id(raw_message: object) -> str | None:
    if not isinstance(raw_message, str):
        return None
    try:
        value = json.loads(raw_message)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    delivery_id = value.get("delivery_id")
    return delivery_id if isinstance(delivery_id, str) else None


async def _run_callback(callback: UrlCallback, received: ReceivedUrl) -> None:
    if inspect.iscoroutinefunction(callback):
        await callback(received)
        return
    result = await asyncio.to_thread(callback, received)
    if inspect.isawaitable(result):
        await result

