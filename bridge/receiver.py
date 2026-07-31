"""PC-side receiver for encrypted Phone-to-PC messages."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
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
POLL_INTERVAL_SECONDS = 1.0


class PcReceiver:
    """Maintain a relay connection and fail closed on bad messages."""

    def __init__(
        self,
        *,
        relay_origin: str,
        credentials: ReceiverCredentials | Sequence[ReceiverCredentials],
        on_url: UrlCallback,
        replay_guard: InMemoryReplayGuard | None = None,
    ) -> None:
        self.relay_origin = normalize_relay_origin(relay_origin)
        credential_items = (
            (credentials,)
            if isinstance(credentials, ReceiverCredentials)
            else tuple(credentials)
        )
        if not credential_items:
            raise ValueError("at least one receiver credential is required")
        first = credential_items[0]
        if any(
            item.device_id != first.device_id
            or item.receiver_token != first.receiver_token
            for item in credential_items
        ):
            raise ValueError(
                "receiver credentials must belong to one relay device"
            )
        if len({item.pair_id for item in credential_items}) != len(
            credential_items
        ):
            raise ValueError("receiver credentials contain a duplicate pair")
        self.credentials = first
        self._credentials_by_pair = {
            item.pair_id: item for item in credential_items
        }
        self.on_url = on_url
        self.replay_guard = replay_guard or InMemoryReplayGuard()
        self.connected = asyncio.Event()

    async def run(self, *, stop_after: int | None = None) -> None:
        """Receive until cancelled or until ``stop_after`` valid URLs."""

        hostname = (urlsplit(self.relay_origin).hostname or "").lower()
        if hostname in {"127.0.0.1", "::1", "localhost"}:
            await self._run_websocket(stop_after=stop_after)
            return
        await self._run_polling(stop_after=stop_after)

    async def _run_websocket(self, *, stop_after: int | None) -> None:
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
                    received, acknowledgement = self._decrypt_event(event)
                except (ProtocolViolation, ValueError, json.JSONDecodeError):
                    delivery_id = _best_effort_delivery_id(raw_message)
                    if delivery_id is not None:
                        await websocket.send(
                            _event_json("delivery_error", delivery_id)
                        )
                    continue

                await websocket.send(
                    _event_json(
                        "delivery_ack",
                        event["delivery_id"],
                        envelope=acknowledgement,
                    )
                )
                await _run_callback(self.on_url, received)
                delivered += 1
                if stop_after is not None and delivered >= stop_after:
                    return

    async def _run_polling(self, *, stop_after: int | None) -> None:
        delivered = 0
        headers = {
            "Authorization": f"Bearer {self.credentials.receiver_token}"
        }
        path = f"/v1/devices/{self.credentials.device_id}/messages"
        async with httpx.AsyncClient(
            base_url=self.relay_origin,
            timeout=8,
            headers=headers,
        ) as client:
            while True:
                response = await client.get(path)
                if response.status_code == 204:
                    self.connected.set()
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue
                response.raise_for_status()
                self.connected.set()
                raw_event: object = response.json()
                try:
                    event = _parse_delivery_event(raw_event)
                    received, acknowledgement = self._decrypt_event(event)
                except (ProtocolViolation, ValueError, json.JSONDecodeError):
                    delivery_id = _best_effort_delivery_id(raw_event)
                    if delivery_id is not None:
                        await client.post(
                            f"/v1/devices/{self.credentials.device_id}"
                            f"/deliveries/{delivery_id}",
                            json={
                                "event": "delivery_error",
                                "delivery_id": delivery_id,
                            },
                        )
                    continue

                acknowledgement_response = await client.post(
                    f"/v1/devices/{self.credentials.device_id}"
                    f"/deliveries/{event['delivery_id']}",
                    json={
                        "event": "delivery_ack",
                        "delivery_id": event["delivery_id"],
                        "envelope": acknowledgement,
                    },
                )
                acknowledgement_response.raise_for_status()
                await _run_callback(self.on_url, received)
                delivered += 1
                if stop_after is not None and delivered >= stop_after:
                    return

    def _decrypt_event(
        self,
        event: dict[str, Any],
    ) -> tuple[ReceivedUrl, dict[str, Any]]:
        pair_id = event["envelope"].get("pair_id")
        credentials = self._credentials_by_pair.get(pair_id)
        if credentials is None:
            raise ProtocolViolation("message belongs to an unknown pair")
        received = decrypt_url_envelope(
            credentials,
            event["envelope"],
            replay_guard=self.replay_guard,
        )
        return (
            received,
            build_delivery_ack(credentials, received.message_id),
        )


def _websocket_url(origin: str, path: str) -> str:
    parsed = urlsplit(origin)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunsplit((scheme, parsed.netloc, path, "", ""))


def _parse_delivery_event(raw_message: object) -> dict[str, Any]:
    value = (
        json.loads(raw_message)
        if isinstance(raw_message, str)
        else raw_message
    )
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
    if isinstance(raw_message, str):
        try:
            value = json.loads(raw_message)
        except json.JSONDecodeError:
            return None
    else:
        value = raw_message
    if not isinstance(value, dict):
        return None
    delivery_id = value.get("delivery_id")
    return delivery_id if isinstance(delivery_id, str) else None


def _event_json(
    event: str,
    delivery_id: str,
    *,
    envelope: dict[str, Any] | None = None,
) -> str:
    value: dict[str, Any] = {
        "event": event,
        "delivery_id": delivery_id,
    }
    if envelope is not None:
        value["envelope"] = envelope
    return json.dumps(value, separators=(",", ":"))


async def _run_callback(callback: UrlCallback, received: ReceivedUrl) -> None:
    if inspect.iscoroutinefunction(callback):
        await callback(received)
        return
    result = await asyncio.to_thread(callback, received)
    if inspect.isawaitable(result):
        await result
