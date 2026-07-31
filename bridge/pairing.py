"""HTTP transport for the short-lived WQRS/1 phone-to-PC pairing flow."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from bridge.protocol import (
    PROTOCOL,
    ApprovedPairing,
    PcPairingSession,
    PhonePairingAttempt,
    ReceiverCredentials,
    SenderCredentials,
    VerifiedPairingRequest,
    approve_pairing_request,
    create_pc_pairing_session,
    decrypt_pairing_request,
    decrypt_pairing_result,
    normalize_relay_origin,
    reject_pairing_request,
)


DEFAULT_POLL_INTERVAL_SECONDS = 0.5
ReceiverPersistence = Callable[
    [ReceiverCredentials],
    None | Awaitable[None],
]


class PairingTransportError(RuntimeError):
    """A stable relay error code suitable for mapping to local UI text."""

    def __init__(self, *, status_code: int, code: str) -> None:
        super().__init__(f"pairing relay rejected request: {code} ({status_code})")
        self.status_code = status_code
        self.code = code


class PairingWaitTimeout(TimeoutError):
    """Raised when the local wait ends before the two-minute QR expiry."""


class PairingWaitCancelled(RuntimeError):
    """Raised when the desktop closes an unfinished pairing wait."""


@dataclass(frozen=True, slots=True)
class PcPairingDecision:
    """Result retained by the PC after approving or rejecting one request."""

    receiver: ReceiverCredentials | None
    phone_label: str
    approved: bool


async def open_pc_pairing(
    *,
    relay_origin: str,
    device_id: str,
    receiver_token: str,
) -> PcPairingSession:
    """Ask the relay for one short session and build its private PC QR data."""

    origin = normalize_relay_origin(relay_origin)
    async with _client(origin) as client:
        response = await client.post(
            "/v1/pairings",
            headers=_authorization(receiver_token),
            json={"protocol": PROTOCOL},
        )
    body = _successful_json(response, expected_status=201)
    if set(body) != {
        "protocol",
        "pairing_id",
        "pairing_token",
        "expires_at",
    } or body.get("protocol") != PROTOCOL:
        raise PairingTransportError(
            status_code=response.status_code,
            code="invalid_relay_response",
        )
    return create_pc_pairing_session(
        relay_origin=origin,
        device_id=device_id,
        receiver_token=receiver_token,
        pairing_id=body["pairing_id"],
        pairing_token=body["pairing_token"],
        expires_at=body["expires_at"],
    )


async def submit_phone_pairing_request(
    attempt: PhonePairingAttempt,
) -> None:
    """Send only the opaque request envelope and QR relay token."""

    async with _client(attempt.qr.relay_origin) as client:
        response = await client.post(
            f"/v1/pairings/{attempt.qr.pairing_id}/request",
            headers=_authorization(attempt.qr.pairing_token),
            json=attempt.request_envelope,
        )
    _successful_json(response, expected_status=202)


async def wait_for_phone_request(
    session: PcPairingSession,
    *,
    timeout_seconds: float | None = None,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    cancellation_event: asyncio.Event | None = None,
) -> VerifiedPairingRequest:
    """Poll for the encrypted phone request, then authenticate it locally."""

    body = await _poll_for_envelope(
        origin=session.qr.relay_origin,
        path=f"/v1/pairings/{session.qr.pairing_id}/request",
        token=session.receiver_token,
        expires_at=session.qr.expires_at,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        cancellation_event=cancellation_event,
    )
    return decrypt_pairing_request(session, body["envelope"])


async def cancel_pc_pairing(session: PcPairingSession) -> None:
    """Invalidate an unneeded pairing QR immediately at the relay."""

    async with _client(session.qr.relay_origin) as client:
        response = await client.delete(
            f"/v1/pairings/{session.qr.pairing_id}",
            headers=_authorization(session.receiver_token),
        )
    _successful_json(response, expected_status=200)


async def complete_pc_pairing(
    session: PcPairingSession,
    request: VerifiedPairingRequest,
    *,
    approved: bool,
    pc_label: str,
    persist_receiver: ReceiverPersistence | None = None,
) -> PcPairingDecision:
    """Publish an encrypted decision and register routing only when approved."""

    if not approved:
        result_envelope = reject_pairing_request(session, request)
        await _store_pairing_result(session, result_envelope)
        return PcPairingDecision(
            receiver=None,
            phone_label=request.phone_label,
            approved=False,
        )

    approval = approve_pairing_request(
        session,
        request,
        pc_label=pc_label,
    )
    await _register_approved_pair(session, approval)
    try:
        if persist_receiver is not None:
            await _run_receiver_persistence(
                persist_receiver,
                approval.receiver,
            )
        await _store_pairing_result(session, approval.result_envelope)
    except Exception:
        await _best_effort_revoke(session, approval.receiver.pair_id)
        raise
    return PcPairingDecision(
        receiver=approval.receiver,
        phone_label=request.phone_label,
        approved=True,
    )


async def _run_receiver_persistence(
    callback: ReceiverPersistence,
    receiver: ReceiverCredentials,
) -> None:
    if inspect.iscoroutinefunction(callback):
        await callback(receiver)
        return
    result = await asyncio.to_thread(callback, receiver)
    if inspect.isawaitable(result):
        await result


async def wait_for_pc_result(
    attempt: PhonePairingAttempt,
    *,
    timeout_seconds: float | None = None,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> SenderCredentials | None:
    """Poll for and authenticate the PC's encrypted approval or rejection."""

    body = await _poll_for_envelope(
        origin=attempt.qr.relay_origin,
        path=f"/v1/pairings/{attempt.qr.pairing_id}/result",
        token=attempt.qr.pairing_token,
        expires_at=attempt.qr.expires_at,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
    )
    return decrypt_pairing_result(attempt, body["envelope"])


async def _register_approved_pair(
    session: PcPairingSession,
    approval: ApprovedPairing,
) -> None:
    async with _client(session.qr.relay_origin) as client:
        response = await client.post(
            "/v1/pairs",
            headers=_authorization(session.receiver_token),
            json={
                "protocol": PROTOCOL,
                "pair_id": approval.receiver.pair_id,
                "sender_token": approval.sender_token,
            },
        )
    _successful_json(response, expected_status=201)


async def _store_pairing_result(
    session: PcPairingSession,
    envelope: dict[str, Any],
) -> None:
    async with _client(session.qr.relay_origin) as client:
        response = await client.post(
            f"/v1/pairings/{session.qr.pairing_id}/result",
            headers=_authorization(session.receiver_token),
            json=envelope,
        )
    _successful_json(response, expected_status=202)


async def _best_effort_revoke(
    session: PcPairingSession,
    pair_id: str,
) -> None:
    try:
        async with _client(session.qr.relay_origin) as client:
            await client.delete(
                f"/v1/pairs/{pair_id}",
                headers=_authorization(session.receiver_token),
            )
    except (httpx.HTTPError, ValueError):
        pass


async def _poll_for_envelope(
    *,
    origin: str,
    path: str,
    token: str,
    expires_at: int,
    timeout_seconds: float | None,
    poll_interval_seconds: float,
    cancellation_event: asyncio.Event | None = None,
) -> dict[str, Any]:
    if poll_interval_seconds <= 0:
        raise ValueError("poll interval must be positive")
    remaining_session = max(0.0, expires_at - time.time())
    actual_timeout = remaining_session
    if timeout_seconds is not None:
        if timeout_seconds <= 0:
            raise ValueError("pairing wait timeout must be positive")
        actual_timeout = min(actual_timeout, timeout_seconds)
    deadline = time.monotonic() + actual_timeout
    async with _client(origin) as client:
        while True:
            if (
                cancellation_event is not None
                and cancellation_event.is_set()
            ):
                raise PairingWaitCancelled("pairing wait was cancelled")
            response = await client.get(path, headers=_authorization(token))
            if response.status_code == 200:
                body = _successful_json(response, expected_status=200)
                if not isinstance(body.get("envelope"), dict):
                    raise PairingTransportError(
                        status_code=200,
                        code="invalid_relay_response",
                    )
                return body
            if response.status_code != 202:
                _raise_response_error(response)
            if time.monotonic() >= deadline:
                raise PairingWaitTimeout("pairing request timed out")
            sleep_seconds = min(
                poll_interval_seconds,
                max(0.0, deadline - time.monotonic()),
            )
            if cancellation_event is None:
                await asyncio.sleep(sleep_seconds)
                continue
            try:
                await asyncio.wait_for(
                    cancellation_event.wait(),
                    timeout=sleep_seconds,
                )
            except TimeoutError:
                continue
            raise PairingWaitCancelled("pairing wait was cancelled")


def _client(origin: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=normalize_relay_origin(origin),
        timeout=5,
    )


def _authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _successful_json(
    response: httpx.Response,
    *,
    expected_status: int,
) -> dict[str, Any]:
    if response.status_code != expected_status:
        _raise_response_error(response)
    try:
        body = response.json()
    except ValueError:
        raise PairingTransportError(
            status_code=response.status_code,
            code="invalid_relay_response",
        ) from None
    if not isinstance(body, dict):
        raise PairingTransportError(
            status_code=response.status_code,
            code="invalid_relay_response",
        )
    return body


def _raise_response_error(response: httpx.Response) -> None:
    code = "invalid_relay_response"
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            code = error["code"]
    raise PairingTransportError(
        status_code=response.status_code,
        code=code,
    )
