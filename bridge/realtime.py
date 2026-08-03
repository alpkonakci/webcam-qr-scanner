"""Supabase Auth and private Realtime wake-ups for the public relay."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from websockets.asyncio.client import connect

from bridge.protocol import PROTOCOL, normalize_relay_origin


MAX_TOKEN_LENGTH = 4096
SESSION_REFRESH_MARGIN_SECONDS = 60
REALTIME_HEARTBEAT_SECONDS = 25.0
REALTIME_RECONNECT_DELAYS_SECONDS = (1.0, 2.0, 5.0, 10.0)
UUID_LENGTH = 36


class RealtimeTransportError(RuntimeError):
    """Raised when Supabase Auth or Realtime returns an unsafe response."""


@dataclass(frozen=True, slots=True)
class RealtimeConfig:
    supabase_url: str
    publishable_key: str
    fallback_poll_seconds: float = 5.0
    connected_resync_seconds: float = 60.0


@dataclass(frozen=True, slots=True)
class RealtimeSession:
    access_token: str
    refresh_token: str
    expires_at: int
    user_id: str


SessionCallback = Callable[[RealtimeSession], None | Awaitable[None]]
WakeupCallback = Callable[[], None]
ConnectionCallback = Callable[[bool], None]


async def fetch_realtime_config(relay_origin: str) -> RealtimeConfig | None:
    """Return public Realtime settings, or ``None`` for the legacy relay."""

    origin = normalize_relay_origin(relay_origin)
    async with httpx.AsyncClient(base_url=origin, timeout=5) as client:
        response = await client.get("/v1/realtime/config")
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise RealtimeTransportError(
            f"Realtime configuration failed with HTTP {response.status_code}"
        )
    try:
        value = response.json()
    except ValueError as error:
        raise RealtimeTransportError(
            "Realtime configuration is not valid JSON"
        ) from error
    if not isinstance(value, dict) or set(value) != {
        "protocol",
        "url",
        "publishableKey",
        "fallback_poll_seconds",
        "connected_resync_seconds",
    }:
        raise RealtimeTransportError("Realtime configuration fields are invalid")
    if value["protocol"] != PROTOCOL:
        raise RealtimeTransportError("Realtime protocol is unsupported")
    supabase_url = normalize_relay_origin(value["url"])
    if not supabase_url.startswith("https://"):
        raise RealtimeTransportError("Supabase Realtime must use HTTPS")
    publishable_key = value["publishableKey"]
    poll_seconds = value["fallback_poll_seconds"]
    resync_seconds = value["connected_resync_seconds"]
    if (
        not isinstance(publishable_key, str)
        or len(publishable_key) < 20
        or len(publishable_key) > MAX_TOKEN_LENGTH
        or any(character.isspace() for character in publishable_key)
        or type(poll_seconds) not in {int, float}
        or not 1 <= float(poll_seconds) <= 30
        or type(resync_seconds) not in {int, float}
        or not 30 <= float(resync_seconds) <= 300
    ):
        raise RealtimeTransportError("Realtime configuration values are invalid")
    return RealtimeConfig(
        supabase_url=supabase_url,
        publishable_key=publishable_key,
        fallback_poll_seconds=float(poll_seconds),
        connected_resync_seconds=float(resync_seconds),
    )


async def create_anonymous_session(config: RealtimeConfig) -> RealtimeSession:
    """Create a device-only session; no email, phone number, or profile."""

    response = await _auth_request(
        config,
        "/auth/v1/signup",
        body={},
    )
    return _parse_session(response)


async def refresh_session(
    config: RealtimeConfig,
    session: RealtimeSession,
) -> RealtimeSession:
    """Rotate an expiring anonymous session using its DPAPI-protected token."""

    response = await _auth_request(
        config,
        "/auth/v1/token?grant_type=refresh_token",
        body={"refresh_token": session.refresh_token},
    )
    refreshed = _parse_session(response)
    if refreshed.user_id != session.user_id:
        raise RealtimeTransportError("Refreshed Realtime identity changed")
    return refreshed


async def ensure_fresh_session(
    config: RealtimeConfig,
    session: RealtimeSession,
) -> RealtimeSession:
    if session.expires_at > int(time.time()) + SESSION_REFRESH_MARGIN_SECONDS:
        return session
    return await refresh_session(config, session)


class RealtimeWakeupClient:
    """Reconnect a private device channel and emit delivery wake-ups."""

    def __init__(
        self,
        *,
        config: RealtimeConfig,
        session: RealtimeSession,
        device_id: str,
        on_wakeup: WakeupCallback,
        on_session: SessionCallback | None = None,
        on_connection_change: ConnectionCallback | None = None,
    ) -> None:
        self.config = config
        self.session = session
        self.device_id = device_id
        self.on_wakeup = on_wakeup
        self.on_session = on_session
        self.on_connection_change = on_connection_change
        self.connected = asyncio.Event()

    async def run(self) -> None:
        """Keep trying Realtime; the caller polls every five seconds only offline."""

        attempt = 0
        while True:
            self._set_connected(False)
            try:
                self.session = await ensure_fresh_session(
                    self.config,
                    self.session,
                )
                await _run_session_callback(self.on_session, self.session)
                await self._run_connected()
                attempt = 0
            except asyncio.CancelledError:
                self._set_connected(False)
                raise
            except Exception:
                self._set_connected(False)
                delay = REALTIME_RECONNECT_DELAYS_SECONDS[
                    min(attempt, len(REALTIME_RECONNECT_DELAYS_SECONDS) - 1)
                ]
                attempt += 1
                await asyncio.sleep(delay)

    async def _run_connected(self) -> None:
        websocket_url = _realtime_websocket_url(self.config)
        topic = f"realtime:device:{self.device_id}"
        join_reference = "1"
        message_reference = 1
        async with connect(
            websocket_url,
            max_size=16 * 1024,
            open_timeout=8,
            close_timeout=2,
        ) as websocket:
            await websocket.send(
                json.dumps(
                    [
                        join_reference,
                        str(message_reference),
                        topic,
                        "phx_join",
                        {
                            "config": {
                                "private": True,
                                "broadcast": {"ack": False, "self": False},
                                "presence": {"enabled": False},
                                "postgres_changes": [],
                            },
                            "access_token": self.session.access_token,
                        },
                    ],
                    separators=(",", ":"),
                )
            )
            heartbeat = asyncio.create_task(
                _heartbeat_loop(websocket),
                name="supabase-realtime-heartbeat",
            )
            renew_after = max(
                1.0,
                self.session.expires_at
                - time.time()
                - SESSION_REFRESH_MARGIN_SECONDS,
            )
            try:
                async with asyncio.timeout(renew_after):
                    joined = False
                    async for raw_message in websocket:
                        value = _parse_realtime_frame(raw_message)
                        event = value[3]
                        payload = value[4]
                        if event == "phx_reply" and value[1] == "1":
                            if not isinstance(
                                payload,
                                dict,
                            ) or payload.get("status") != "ok":
                                raise RealtimeTransportError(
                                    "Private Realtime channel was rejected"
                                )
                            joined = True
                            self._set_connected(True)
                            continue
                        if event in {"phx_error", "phx_close"}:
                            raise RealtimeTransportError(
                                "Private Realtime channel disconnected"
                            )
                        if event == "system" and _system_error(payload):
                            raise RealtimeTransportError(
                                "Private Realtime channel reported an error"
                            )
                        if event == "broadcast" and joined:
                            if _is_delivery_wakeup(payload):
                                self.on_wakeup()
            except TimeoutError as error:
                raise RealtimeTransportError(
                    "Realtime session refresh is required"
                ) from error
            finally:
                self._set_connected(False)
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)

    def _set_connected(self, value: bool) -> None:
        previous = self.connected.is_set()
        if value:
            self.connected.set()
        else:
            self.connected.clear()
        if previous != value and self.on_connection_change is not None:
            self.on_connection_change(value)


async def _auth_request(
    config: RealtimeConfig,
    path: str,
    *,
    body: dict[str, str],
) -> object:
    async with httpx.AsyncClient(base_url=config.supabase_url, timeout=8) as client:
        response = await client.post(
            path,
            headers={
                "apikey": config.publishable_key,
                "Content-Type": "application/json",
            },
            json=body,
        )
    if response.status_code not in {200, 201}:
        raise RealtimeTransportError(
            f"Supabase anonymous authentication failed with HTTP {response.status_code}"
        )
    try:
        return response.json()
    except ValueError as error:
        raise RealtimeTransportError(
            "Supabase authentication returned invalid JSON"
        ) from error


def _parse_session(value: object) -> RealtimeSession:
    if not isinstance(value, dict):
        raise RealtimeTransportError("Supabase session is invalid")
    access_token = value.get("access_token")
    refresh_token = value.get("refresh_token")
    expires_at = value.get("expires_at")
    expires_in = value.get("expires_in")
    user = value.get("user")
    user_id = user.get("id") if isinstance(user, dict) else None
    if expires_at is None and type(expires_in) is int:
        expires_at = int(time.time()) + expires_in
    if (
        not _valid_token(access_token)
        or not _valid_token(refresh_token)
        or type(expires_at) is not int
        or expires_at <= int(time.time())
        or not isinstance(user_id, str)
        or not _valid_uuid(user_id)
    ):
        raise RealtimeTransportError("Supabase session fields are invalid")
    return RealtimeSession(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        user_id=user_id,
    )


def _realtime_websocket_url(config: RealtimeConfig) -> str:
    parsed = urlsplit(config.supabase_url)
    query = urlencode({"apikey": config.publishable_key, "vsn": "2.0.0"})
    return urlunsplit(("wss", parsed.netloc, "/realtime/v1/websocket", query, ""))


async def _heartbeat_loop(websocket: object) -> None:
    reference = 2
    while True:
        await asyncio.sleep(REALTIME_HEARTBEAT_SECONDS)
        await websocket.send(
            json.dumps(
                [None, str(reference), "phoenix", "heartbeat", {}],
                separators=(",", ":"),
            )
        )
        reference += 1


def _parse_realtime_frame(raw_message: object) -> list[object]:
    if not isinstance(raw_message, str):
        raise RealtimeTransportError("Binary Realtime frame is unsupported")
    try:
        value = json.loads(raw_message)
    except json.JSONDecodeError as error:
        raise RealtimeTransportError("Realtime frame is invalid JSON") from error
    if (
        not isinstance(value, list)
        or len(value) != 5
        or not isinstance(value[2], str)
        or not isinstance(value[3], str)
    ):
        raise RealtimeTransportError("Realtime frame fields are invalid")
    return value


def _is_delivery_wakeup(payload: object) -> bool:
    if not isinstance(payload, dict) or payload.get("event") != "delivery_ready":
        return False
    inner = payload.get("payload")
    delivery_id = inner.get("delivery_id") if isinstance(inner, dict) else None
    return (
        isinstance(delivery_id, str)
        and len(delivery_id) == 22
        and all(character.isalnum() or character in "_-" for character in delivery_id)
    )


def _system_error(payload: object) -> bool:
    return isinstance(payload, dict) and payload.get("status") == "error"


async def _run_session_callback(
    callback: SessionCallback | None,
    session: RealtimeSession,
) -> None:
    if callback is None:
        return
    if inspect.iscoroutinefunction(callback):
        await callback(session)
        return
    result = await asyncio.to_thread(callback, session)
    if inspect.isawaitable(result):
        await result


def _valid_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and 20 <= len(value) <= MAX_TOKEN_LENGTH
        and not any(character.isspace() for character in value)
    )


def _valid_uuid(value: str) -> bool:
    if len(value) != UUID_LENGTH:
        return False
    groups = value.split("-")
    if [len(group) for group in groups] != [8, 4, 4, 4, 12]:
        return False
    try:
        int("".join(groups), 16)
    except ValueError:
        return False
    return True
