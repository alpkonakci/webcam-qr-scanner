"""Desktop orchestration for QR display, approval, and secure persistence."""

from __future__ import annotations

import asyncio
import contextlib
import os
import platform
import threading
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

import httpx

from bridge.pairing import (
    PairingTransportError,
    PairingWaitCancelled,
    PairingWaitTimeout,
    cancel_pc_pairing,
    complete_pc_pairing,
    open_pc_pairing,
    wait_for_phone_request,
)
from bridge.protocol import (
    PROTOCOL,
    PcPairingSession,
    ReceiverCredentials,
    b64url_decode,
    normalize_relay_origin,
)
from bridge.secure_storage import (
    PairingStore,
    RelayDevice,
    StoredPair,
)
from native_dialogs import confirm_phone_pairing
from pairing_ui import PairingWindowOutcome, show_pairing_qr_window


PUBLIC_RELAY_ORIGIN = "https://webcam-qr-scanner-pwa.alpkon.chatgpt.site"
LOCAL_DEVELOPMENT_RELAY_ORIGIN = "http://127.0.0.1:8765"
RELAY_ENVIRONMENT_VARIABLE = "WQRS_RELAY_ORIGIN"


class PairingControllerStatus(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class PairingControllerResult:
    status: PairingControllerStatus
    phone_label: str | None = None


class PairingController:
    """Run one pairing attempt without blocking the tray event loop."""

    def __init__(
        self,
        *,
        relay_origin: str,
        store: PairingStore | None = None,
        pc_label: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.relay_origin = normalize_relay_origin(relay_origin)
        self.store = store or PairingStore()
        self.pc_label = _safe_pc_label(pc_label)
        self.cancel_event = cancel_event

    def run(self) -> PairingControllerResult:
        return asyncio.run(self._run())

    async def _run(self) -> PairingControllerResult:
        session = await self._open_session_with_current_device()
        request_received = threading.Event()
        stop_waiting = asyncio.Event()
        request_task = asyncio.create_task(
            wait_for_phone_request(
                session,
                cancellation_event=stop_waiting,
            ),
            name="wait-for-phone-pairing-request",
        )
        window_task = asyncio.create_task(
            asyncio.to_thread(
                show_pairing_qr_window,
                session.pairing_uri,
                expires_at=session.qr.expires_at,
                request_received=request_received,
                cancel_requested=self.cancel_event,
                relay_origin=self.relay_origin,
                development_mode=_is_loopback_origin(self.relay_origin),
            ),
            name="pairing-qr-window",
        )
        done, _ = await asyncio.wait(
            {request_task, window_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if window_task in done:
            outcome = window_task.result()
            stop_waiting.set()
            with contextlib.suppress(
                PairingWaitCancelled,
                PairingWaitTimeout,
                PairingTransportError,
            ):
                await request_task
            await _best_effort_cancel_pairing(session)
            return PairingControllerResult(
                status=(
                    PairingControllerStatus.EXPIRED
                    if outcome is PairingWindowOutcome.EXPIRED
                    else PairingControllerStatus.CANCELLED
                )
            )

        request_received.set()
        await window_task
        try:
            request = request_task.result()
        except PairingWaitTimeout:
            await _best_effort_cancel_pairing(session)
            return PairingControllerResult(
                status=PairingControllerStatus.EXPIRED
            )
        approved = await asyncio.to_thread(
            confirm_phone_pairing,
            request.phone_label,
            relay_origin=self.relay_origin,
        )

        def persist_receiver(credentials: ReceiverCredentials) -> None:
            self.store.add_pair(
                StoredPair(
                    relay_origin=self.relay_origin,
                    device_id=credentials.device_id,
                    pair_id=credentials.pair_id,
                    root_key=credentials.root_key,
                    phone_label=request.phone_label,
                    key_epoch=credentials.key_epoch,
                )
            )

        decision = await complete_pc_pairing(
            session,
            request,
            approved=approved,
            pc_label=self.pc_label,
            persist_receiver=persist_receiver if approved else None,
        )
        return PairingControllerResult(
            status=(
                PairingControllerStatus.APPROVED
                if decision.approved
                else PairingControllerStatus.REJECTED
            ),
            phone_label=decision.phone_label,
        )

    async def _open_session_with_current_device(self) -> PcPairingSession:
        device = self.store.load().device_for(self.relay_origin)
        if device is None:
            device = await self._register_device(clear_old_pairs=False)
        try:
            return await open_pc_pairing(
                relay_origin=self.relay_origin,
                device_id=device.device_id,
                receiver_token=device.receiver_token,
            )
        except PairingTransportError as error:
            if error.code != "unauthorized":
                raise
        device = await self._register_device(clear_old_pairs=True)
        return await open_pc_pairing(
            relay_origin=self.relay_origin,
            device_id=device.device_id,
            receiver_token=device.receiver_token,
        )

    async def _register_device(self, *, clear_old_pairs: bool) -> RelayDevice:
        async with httpx.AsyncClient(
            base_url=self.relay_origin,
            timeout=5,
        ) as client:
            response = await client.post("/v1/devices")
        if response.status_code != 201:
            raise PairingTransportError(
                status_code=response.status_code,
                code=_response_error_code(response),
            )
        try:
            body = response.json()
        except ValueError:
            body = None
        if (
            not isinstance(body, dict)
            or set(body) != {"protocol", "device_id", "receiver_token"}
            or body.get("protocol") != PROTOCOL
        ):
            raise PairingTransportError(
                status_code=response.status_code,
                code="invalid_relay_response",
            )
        b64url_decode(body["device_id"], expected_length=16)
        b64url_decode(body["receiver_token"], expected_length=32)
        device = RelayDevice(
            relay_origin=self.relay_origin,
            device_id=body["device_id"],
            receiver_token=body["receiver_token"],
        )
        self.store.replace_device(
            device,
            clear_pairs=clear_old_pairs,
        )
        return device


def configured_relay_origin(
    environment: dict[str, str] | None = None,
) -> str:
    """Use an explicit relay override or the official public beta relay."""

    source = os.environ if environment is None else environment
    return normalize_relay_origin(
        source.get(RELAY_ENVIRONMENT_VARIABLE, PUBLIC_RELAY_ORIGIN)
    )


def _safe_pc_label(value: str | None) -> str:
    candidate = (value if value is not None else platform.node()).strip()
    candidate = "".join(
        character
        for character in candidate
        if ord(character) >= 32 and ord(character) != 127
    )
    return (candidate or "Windows PC")[:80]


def _is_loopback_origin(origin: str) -> bool:
    return (urlsplit(origin).hostname or "").lower() in {
        "127.0.0.1",
        "::1",
        "localhost",
    }


def _response_error_code(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return "invalid_relay_response"
    if not isinstance(body, dict):
        return "invalid_relay_response"
    error = body.get("error")
    if not isinstance(error, dict) or not isinstance(error.get("code"), str):
        return "invalid_relay_response"
    return error["code"]


async def _best_effort_cancel_pairing(session: PcPairingSession) -> None:
    try:
        await cancel_pc_pairing(session)
    except (httpx.HTTPError, PairingTransportError, ValueError):
        pass
