"""Command-line fake phone used to exercise WQRS/1 before the PWA exists."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from bridge.protocol import (
    SenderCredentials,
    build_url_envelope,
    normalize_relay_origin,
    verify_delivery_ack,
)


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    message_id: str
    status: str


class DeliveryFailed(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        super().__init__(f"relay rejected delivery: {code} ({status_code})")
        self.status_code = status_code
        self.code = code


class FakePhone:
    """Encrypt URLs locally and send only opaque envelopes to the relay."""

    def __init__(
        self,
        *,
        relay_origin: str,
        credentials: SenderCredentials,
        timeout_seconds: float = 15,
    ) -> None:
        self.relay_origin = normalize_relay_origin(relay_origin)
        self.credentials = credentials
        self.timeout_seconds = timeout_seconds

    async def send_url(self, url: str) -> DeliveryResult:
        envelope = build_url_envelope(self.credentials, url)
        return await self.send_envelope(envelope)

    async def send_envelope(
        self,
        envelope: dict[str, Any],
        *,
        verify_ack: bool = True,
    ) -> DeliveryResult:
        message_id = envelope.get("message_id")
        if not isinstance(message_id, str):
            raise ValueError("envelope has no string message_id")
        async with httpx.AsyncClient(
            base_url=self.relay_origin,
            timeout=self.timeout_seconds,
        ) as client:
            response = await client.post(
                f"/v1/pairs/{self.credentials.pair_id}/messages",
                headers={
                    "Authorization": (
                        f"Bearer {self.credentials.sender_token}"
                    )
                },
                json=envelope,
            )
        if response.status_code != 200:
            raise DeliveryFailed(
                status_code=response.status_code,
                code=_error_code(response),
            )
        body = response.json()
        acknowledgement = body.get("ack")
        if verify_ack:
            verify_delivery_ack(
                self.credentials,
                acknowledgement,
                expected_message_id=message_id,
            )
        return DeliveryResult(
            message_id=message_id,
            status=str(body.get("status", "")),
        )


def _error_code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return "invalid_relay_response"
    if not isinstance(body, dict):
        return "invalid_relay_response"
    error = body.get("error")
    if not isinstance(error, dict):
        return "invalid_relay_response"
    code = error.get("code")
    return code if isinstance(code, str) else "invalid_relay_response"

