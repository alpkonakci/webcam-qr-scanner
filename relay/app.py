"""FastAPI application for the localhost-only WQRS/1 relay prototype."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from bridge.protocol import PROTOCOL, ProtocolViolation, random_b64url
from relay.state import PairingStateError, RelayState


MAX_REQUEST_BYTES = 12 * 1024
DELIVERY_TIMEOUT_SECONDS = 10
MESSAGE_ENVELOPE_FIELDS = frozenset(
    {
        "protocol",
        "type",
        "pair_id",
        "key_epoch",
        "message_id",
        "created_at",
        "expires_at",
        "nonce",
        "ciphertext",
    }
)
PAIRING_ENVELOPE_FIELDS = frozenset(
    {
        "protocol",
        "device_id",
        "pairing_id",
        "phone_public_key",
        "expires_at",
        "type",
        "created_at",
        "nonce",
        "ciphertext",
    }
)


@dataclass(slots=True)
class PendingDelivery:
    device_id: str
    future: asyncio.Future[dict[str, Any]]


class RelayApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds


def create_app(relay_state: RelayState | None = None) -> FastAPI:
    """Create an isolated relay instance with no persistent message storage."""

    routes = relay_state or RelayState()
    pending: dict[str, PendingDelivery] = {}
    pending_lock = asyncio.Lock()
    app = FastAPI(
        title="Webcam QR Scanner local relay",
        version="0.2.0-dev",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.relay = routes

    @app.exception_handler(RelayApiError)
    async def relay_error_handler(
        _: Request,
        error: RelayApiError,
    ) -> JSONResponse:
        body: dict[str, object] = {
            "error": {
                "code": error.code,
                "message": error.message,
            }
        }
        if error.retry_after_seconds is not None:
            body["error"]["retry_after_seconds"] = error.retry_after_seconds
        return JSONResponse(body, status_code=error.status_code)

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok", "protocol": PROTOCOL}

    @app.post("/v1/devices", status_code=201)
    async def create_device() -> dict[str, str]:
        device_id, receiver_token = routes.create_device()
        return {
            "protocol": PROTOCOL,
            "device_id": device_id,
            "receiver_token": receiver_token,
        }

    @app.post("/v1/pairings", status_code=201)
    async def create_pairing(request: Request) -> dict[str, object]:
        receiver_token = _bearer_token(request.headers.get("authorization"))
        device_id = routes.device_for_receiver_token(receiver_token)
        if device_id is None:
            raise RelayApiError(401, "unauthorized", "Receiver token is invalid.")
        body = await _read_json_object(request)
        if body != {"protocol": PROTOCOL}:
            raise RelayApiError(
                400,
                "invalid_request",
                "Pairing request fields are invalid.",
            )
        pairing_id, pairing_token, expires_at = routes.create_pairing(
            device_id=device_id
        )
        return {
            "protocol": PROTOCOL,
            "pairing_id": pairing_id,
            "pairing_token": pairing_token,
            "expires_at": expires_at,
        }

    @app.post("/v1/pairings/{pairing_id}/request", status_code=202)
    async def submit_pairing_request(
        pairing_id: str,
        request: Request,
    ) -> dict[str, str]:
        pairing_token = _bearer_token(request.headers.get("authorization"))
        envelope = await _read_json_object(request)
        _validate_pairing_envelope_shape(
            envelope,
            pairing_id=pairing_id,
            expected_type="pair_request",
        )
        try:
            routes.submit_pairing_request(
                pairing_id=pairing_id,
                pairing_token=pairing_token,
                envelope=envelope,
            )
        except PairingStateError as error:
            _raise_pairing_api_error(error)
        return {"status": "waiting_for_pc", "pairing_id": pairing_id}

    @app.get("/v1/pairings/{pairing_id}/request")
    async def get_pairing_request(
        pairing_id: str,
        request: Request,
    ) -> JSONResponse:
        receiver_token = _bearer_token(request.headers.get("authorization"))
        device_id = routes.device_for_receiver_token(receiver_token)
        if device_id is None:
            raise RelayApiError(401, "unauthorized", "Receiver token is invalid.")
        try:
            envelope = routes.pairing_request_for_receiver(
                device_id=device_id,
                pairing_id=pairing_id,
            )
        except PairingStateError as error:
            _raise_pairing_api_error(error)
        if envelope is None:
            return JSONResponse(
                {
                    "status": "waiting_for_phone",
                    "pairing_id": pairing_id,
                },
                status_code=202,
            )
        return JSONResponse(
            {
                "status": "request_received",
                "pairing_id": pairing_id,
                "envelope": envelope,
            }
        )

    @app.delete("/v1/pairings/{pairing_id}")
    async def cancel_pairing(
        pairing_id: str,
        request: Request,
    ) -> dict[str, str]:
        receiver_token = _bearer_token(request.headers.get("authorization"))
        device_id = routes.device_for_receiver_token(receiver_token)
        if device_id is None:
            raise RelayApiError(401, "unauthorized", "Receiver token is invalid.")
        if not routes.cancel_pairing(
            device_id=device_id,
            pairing_id=pairing_id,
        ):
            raise RelayApiError(
                404,
                "pairing_not_found",
                "Pairing session was not found.",
            )
        return {"status": "cancelled", "pairing_id": pairing_id}

    @app.post("/v1/pairings/{pairing_id}/result", status_code=202)
    async def store_pairing_result(
        pairing_id: str,
        request: Request,
    ) -> dict[str, str]:
        receiver_token = _bearer_token(request.headers.get("authorization"))
        device_id = routes.device_for_receiver_token(receiver_token)
        if device_id is None:
            raise RelayApiError(401, "unauthorized", "Receiver token is invalid.")
        envelope = await _read_json_object(request)
        _validate_pairing_envelope_shape(
            envelope,
            pairing_id=pairing_id,
            expected_type="pair_result",
        )
        try:
            routes.store_pairing_result(
                device_id=device_id,
                pairing_id=pairing_id,
                envelope=envelope,
            )
        except PairingStateError as error:
            _raise_pairing_api_error(error)
        return {"status": "result_available", "pairing_id": pairing_id}

    @app.get("/v1/pairings/{pairing_id}/result")
    async def get_pairing_result(
        pairing_id: str,
        request: Request,
    ) -> JSONResponse:
        pairing_token = _bearer_token(request.headers.get("authorization"))
        try:
            envelope = routes.pairing_result_for_phone(
                pairing_id=pairing_id,
                pairing_token=pairing_token,
            )
        except PairingStateError as error:
            _raise_pairing_api_error(error)
        if envelope is None:
            return JSONResponse(
                {
                    "status": "waiting_for_pc",
                    "pairing_id": pairing_id,
                },
                status_code=202,
            )
        return JSONResponse(
            {
                "status": "result_available",
                "pairing_id": pairing_id,
                "envelope": envelope,
            }
        )

    @app.post("/v1/pairs", status_code=201)
    async def register_pair(request: Request) -> dict[str, str]:
        receiver_token = _bearer_token(request.headers.get("authorization"))
        device_id = routes.device_for_receiver_token(receiver_token)
        if device_id is None:
            raise RelayApiError(401, "unauthorized", "Receiver token is invalid.")
        body = await _read_json_object(request)
        if set(body) != {"protocol", "pair_id", "sender_token"}:
            raise RelayApiError(400, "invalid_request", "Pair fields are invalid.")
        if body["protocol"] != PROTOCOL:
            raise RelayApiError(
                400,
                "unsupported_protocol",
                "Protocol version is unsupported.",
            )
        try:
            routes.register_pair(
                device_id=device_id,
                pair_id=body["pair_id"],
                sender_token=body["sender_token"],
            )
        except (KeyError, ProtocolViolation, TypeError):
            raise RelayApiError(
                400,
                "invalid_request",
                "Pair credentials are invalid.",
            ) from None
        return {"status": "paired", "pair_id": body["pair_id"]}

    @app.delete("/v1/pairs/{pair_id}")
    async def revoke_pair(pair_id: str, request: Request) -> dict[str, str]:
        receiver_token = _bearer_token(request.headers.get("authorization"))
        device_id = routes.device_for_receiver_token(receiver_token)
        if device_id is None:
            raise RelayApiError(401, "unauthorized", "Receiver token is invalid.")
        if not routes.revoke_pair(device_id=device_id, pair_id=pair_id):
            raise RelayApiError(404, "pair_not_found", "Pair was not found.")
        return {"status": "revoked", "pair_id": pair_id}

    @app.post("/v1/pairs/{pair_id}/messages")
    async def send_message(
        pair_id: str,
        request: Request,
    ) -> dict[str, object]:
        sender_token = _bearer_token(request.headers.get("authorization"))
        route = routes.authenticate_sender(
            pair_id=pair_id,
            sender_token=sender_token,
        )
        if route is None:
            raise RelayApiError(401, "unauthorized", "Sender token is invalid.")
        envelope = await _read_json_object(request)
        if (
            set(envelope) != MESSAGE_ENVELOPE_FIELDS
            or envelope.get("protocol") != PROTOCOL
            or envelope.get("type") != "url_message"
            or envelope.get("pair_id") != pair_id
        ):
            raise RelayApiError(
                400,
                "invalid_request",
                "Encrypted envelope metadata is invalid.",
            )
        if len(json.dumps(envelope, separators=(",", ":")).encode("utf-8")) > (
            MAX_REQUEST_BYTES
        ):
            raise RelayApiError(413, "message_too_large", "Message is too large.")
        connection = routes.get_connection(route.device_id)
        if connection is None:
            raise RelayApiError(
                409,
                "receiver_offline",
                "The paired computer is offline.",
                retry_after_seconds=15,
            )

        delivery_id = random_b64url(16)
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        async with pending_lock:
            pending[delivery_id] = PendingDelivery(route.device_id, future)
        try:
            await connection.send_json(
                {
                    "event": "url_message",
                    "delivery_id": delivery_id,
                    "envelope": envelope,
                }
            )
            result = await asyncio.wait_for(
                asyncio.shield(future),
                timeout=DELIVERY_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise RelayApiError(
                504,
                "delivery_timeout",
                "The computer did not acknowledge the message.",
            ) from None
        except (RuntimeError, WebSocketDisconnect):
            raise RelayApiError(
                409,
                "receiver_offline",
                "The paired computer disconnected.",
                retry_after_seconds=15,
            ) from None
        finally:
            async with pending_lock:
                pending.pop(delivery_id, None)

        if result["event"] == "delivery_error":
            raise RelayApiError(
                422,
                "delivery_rejected",
                "The computer rejected the encrypted message.",
            )
        return {
            "status": "delivered",
            "ack": result["envelope"],
        }

    @app.websocket("/v1/devices/{device_id}/connect")
    async def connect_receiver(websocket: WebSocket, device_id: str) -> None:
        try:
            receiver_token = _bearer_token(
                websocket.headers.get("authorization")
            )
        except RelayApiError:
            await websocket.close(code=4401)
            return
        if not routes.authenticate_receiver(
            device_id=device_id,
            receiver_token=receiver_token,
        ):
            await websocket.close(code=4401)
            return

        await websocket.accept()
        routes.set_connection(device_id, websocket)
        try:
            while True:
                message = await websocket.receive_json()
                if not isinstance(message, dict):
                    continue
                event = message.get("event")
                delivery_id = message.get("delivery_id")
                if event not in {"delivery_ack", "delivery_error"}:
                    continue
                if not isinstance(delivery_id, str):
                    continue
                async with pending_lock:
                    item = pending.get(delivery_id)
                    if item is None or item.device_id != device_id:
                        continue
                    if item.future.done():
                        continue
                    if event == "delivery_ack":
                        envelope = message.get("envelope")
                        if not isinstance(envelope, dict):
                            continue
                        item.future.set_result(
                            {"event": event, "envelope": envelope}
                        )
                    else:
                        item.future.set_result({"event": event})
        except (WebSocketDisconnect, RuntimeError, ValueError):
            pass
        finally:
            routes.clear_connection(device_id, websocket)
            async with pending_lock:
                affected = [
                    item.future
                    for item in pending.values()
                    if item.device_id == device_id and not item.future.done()
                ]
            for future in affected:
                future.set_exception(WebSocketDisconnect())

    return app


def _bearer_token(header_value: str | None) -> str:
    if not header_value:
        raise RelayApiError(401, "unauthorized", "Bearer token is required.")
    scheme, separator, token = header_value.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token:
        raise RelayApiError(401, "unauthorized", "Bearer token is invalid.")
    if " " in token:
        raise RelayApiError(401, "unauthorized", "Bearer token is invalid.")
    return token


async def _read_json_object(request: Request) -> dict[str, Any]:
    body = await request.body()
    if len(body) > MAX_REQUEST_BYTES:
        raise RelayApiError(413, "message_too_large", "Request is too large.")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RelayApiError(400, "invalid_request", "JSON body is invalid.") from None
    if not isinstance(value, dict):
        raise RelayApiError(400, "invalid_request", "JSON body must be an object.")
    return value


def _validate_pairing_envelope_shape(
    envelope: dict[str, Any],
    *,
    pairing_id: str,
    expected_type: str,
) -> None:
    if (
        set(envelope) != PAIRING_ENVELOPE_FIELDS
        or envelope.get("protocol") != PROTOCOL
        or envelope.get("type") != expected_type
        or envelope.get("pairing_id") != pairing_id
    ):
        raise RelayApiError(
            400,
            "invalid_request",
            "Encrypted pairing envelope metadata is invalid.",
        )
    if len(json.dumps(envelope, separators=(",", ":")).encode("utf-8")) > (
        MAX_REQUEST_BYTES
    ):
        raise RelayApiError(413, "message_too_large", "Message is too large.")


def _raise_pairing_api_error(error: PairingStateError) -> None:
    status_and_message = {
        "unauthorized": (401, "Pairing token is invalid."),
        "pairing_not_found": (404, "Pairing session was not found."),
        "pairing_expired": (410, "Pairing session has expired."),
        "pairing_already_used": (409, "Pairing session was already used."),
        "pairing_request_missing": (409, "Pairing request has not arrived."),
        "invalid_request": (400, "Pairing envelope does not match the session."),
    }
    status_code, message = status_and_message.get(
        error.code,
        (400, "Pairing state transition is invalid."),
    )
    raise RelayApiError(status_code, error.code, message)
