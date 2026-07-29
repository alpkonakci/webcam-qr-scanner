"""Security-sensitive in-memory routing state for the local relay."""

from __future__ import annotations

import copy
import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

from bridge.protocol import (
    PAIRING_TTL_SECONDS,
    ProtocolViolation,
    b64url_decode,
    random_b64url,
)


@dataclass(frozen=True, slots=True)
class DeviceRoute:
    device_id: str
    receiver_token_digest: bytes


@dataclass(frozen=True, slots=True)
class PairRoute:
    pair_id: str
    device_id: str
    sender_token_digest: bytes


@dataclass(slots=True)
class PairingRoute:
    pairing_id: str
    device_id: str
    pairing_token_digest: bytes
    expires_at: int
    request_envelope: dict[str, Any] | None = None
    result_envelope: dict[str, Any] | None = None


class PairingStateError(RuntimeError):
    """A safe, protocol-level pairing state transition failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RelayState:
    """Store only routing identifiers and keyed token digests.

    Encrypted envelopes live only in individual request/connection call stacks.
    They are never appended to this state, an audit list, or a database.
    """

    def __init__(self, *, token_pepper: bytes | None = None) -> None:
        self._token_pepper = token_pepper or secrets.token_bytes(32)
        self._devices: dict[str, DeviceRoute] = {}
        self._pairs: dict[str, PairRoute] = {}
        self._pairings: dict[str, PairingRoute] = {}
        self._connections: dict[str, Any] = {}
        self._lock = threading.RLock()

    def create_device(self) -> tuple[str, str]:
        device_id = random_b64url(16)
        receiver_token = random_b64url(32)
        route = DeviceRoute(
            device_id=device_id,
            receiver_token_digest=self._token_digest(receiver_token),
        )
        with self._lock:
            self._devices[device_id] = route
        return device_id, receiver_token

    def create_pairing(
        self,
        *,
        device_id: str,
        now: int | None = None,
    ) -> tuple[str, str, int]:
        """Create a two-minute, single-request pairing relay route."""

        current_time = int(time.time()) if now is None else now
        pairing_id = random_b64url(16)
        pairing_token = random_b64url(32)
        route = PairingRoute(
            pairing_id=pairing_id,
            device_id=device_id,
            pairing_token_digest=self._token_digest(pairing_token),
            expires_at=current_time + PAIRING_TTL_SECONDS,
        )
        with self._lock:
            if device_id not in self._devices:
                raise KeyError("device not found")
            self._prune_pairings(current_time)
            self._pairings[pairing_id] = route
        return pairing_id, pairing_token, route.expires_at

    def submit_pairing_request(
        self,
        *,
        pairing_id: str,
        pairing_token: str,
        envelope: dict[str, Any],
        now: int | None = None,
    ) -> str:
        """Store exactly one encrypted request and return its PC device ID."""

        current_time = int(time.time()) if now is None else now
        with self._lock:
            route = self._authenticated_pairing(
                pairing_id=pairing_id,
                pairing_token=pairing_token,
            )
            self._require_active_pairing(route, current_time)
            if route.request_envelope is not None:
                raise PairingStateError("pairing_already_used")
            if (
                envelope.get("pairing_id") != route.pairing_id
                or envelope.get("device_id") != route.device_id
                or envelope.get("expires_at") != route.expires_at
            ):
                raise PairingStateError("invalid_request")
            route.request_envelope = copy.deepcopy(envelope)
            return route.device_id

    def pairing_request_for_receiver(
        self,
        *,
        device_id: str,
        pairing_id: str,
        now: int | None = None,
    ) -> dict[str, Any] | None:
        """Return the opaque phone request only to the owning PC."""

        current_time = int(time.time()) if now is None else now
        with self._lock:
            route = self._receiver_pairing(
                device_id=device_id,
                pairing_id=pairing_id,
            )
            self._require_active_pairing(route, current_time)
            return copy.deepcopy(route.request_envelope)

    def store_pairing_result(
        self,
        *,
        device_id: str,
        pairing_id: str,
        envelope: dict[str, Any],
        now: int | None = None,
    ) -> None:
        """Store one opaque PC decision until the short session expires."""

        current_time = int(time.time()) if now is None else now
        with self._lock:
            route = self._receiver_pairing(
                device_id=device_id,
                pairing_id=pairing_id,
            )
            self._require_active_pairing(route, current_time)
            if route.request_envelope is None:
                raise PairingStateError("pairing_request_missing")
            if route.result_envelope is not None:
                raise PairingStateError("pairing_already_used")
            if (
                envelope.get("pairing_id") != route.pairing_id
                or envelope.get("device_id") != route.device_id
                or envelope.get("expires_at") != route.expires_at
                or envelope.get("phone_public_key")
                != route.request_envelope.get("phone_public_key")
            ):
                raise PairingStateError("invalid_request")
            route.result_envelope = copy.deepcopy(envelope)

    def pairing_result_for_phone(
        self,
        *,
        pairing_id: str,
        pairing_token: str,
        now: int | None = None,
    ) -> dict[str, Any] | None:
        """Return the opaque PC decision only to the QR token holder."""

        current_time = int(time.time()) if now is None else now
        with self._lock:
            route = self._authenticated_pairing(
                pairing_id=pairing_id,
                pairing_token=pairing_token,
            )
            self._require_active_pairing(route, current_time)
            return copy.deepcopy(route.result_envelope)

    def authenticate_receiver(
        self,
        *,
        device_id: str,
        receiver_token: str,
    ) -> bool:
        try:
            b64url_decode(device_id, expected_length=16)
            b64url_decode(receiver_token, expected_length=32)
        except ValueError:
            return False
        with self._lock:
            route = self._devices.get(device_id)
        return route is not None and hmac.compare_digest(
            route.receiver_token_digest,
            self._token_digest(receiver_token),
        )

    def device_for_receiver_token(self, receiver_token: str) -> str | None:
        try:
            b64url_decode(receiver_token, expected_length=32)
        except ValueError:
            return None
        candidate = self._token_digest(receiver_token)
        with self._lock:
            devices = tuple(self._devices.values())
        for route in devices:
            if hmac.compare_digest(route.receiver_token_digest, candidate):
                return route.device_id
        return None

    def register_pair(
        self,
        *,
        device_id: str,
        pair_id: str,
        sender_token: str,
    ) -> None:
        b64url_decode(pair_id, expected_length=16)
        b64url_decode(sender_token, expected_length=32)
        with self._lock:
            if device_id not in self._devices:
                raise KeyError("device not found")
            self._pairs[pair_id] = PairRoute(
                pair_id=pair_id,
                device_id=device_id,
                sender_token_digest=self._token_digest(sender_token),
            )

    def authenticate_sender(
        self,
        *,
        pair_id: str,
        sender_token: str,
    ) -> PairRoute | None:
        try:
            b64url_decode(pair_id, expected_length=16)
            b64url_decode(sender_token, expected_length=32)
        except ValueError:
            return None
        with self._lock:
            route = self._pairs.get(pair_id)
        if route is None or not hmac.compare_digest(
            route.sender_token_digest,
            self._token_digest(sender_token),
        ):
            return None
        return route

    def revoke_pair(self, *, device_id: str, pair_id: str) -> bool:
        with self._lock:
            route = self._pairs.get(pair_id)
            if route is None or route.device_id != device_id:
                return False
            del self._pairs[pair_id]
        return True

    def set_connection(self, device_id: str, connection: Any) -> None:
        with self._lock:
            self._connections[device_id] = connection

    def clear_connection(self, device_id: str, connection: Any) -> None:
        with self._lock:
            if self._connections.get(device_id) is connection:
                del self._connections[device_id]

    def get_connection(self, device_id: str) -> Any | None:
        with self._lock:
            return self._connections.get(device_id)

    def safe_snapshot(self) -> dict[str, object]:
        """Return diagnostics that deliberately exclude tokens and messages."""

        with self._lock:
            return {
                "device_count": len(self._devices),
                "pair_count": len(self._pairs),
                "pairing_count": len(self._pairings),
                "connected_device_count": len(self._connections),
                "device_ids": sorted(self._devices),
                "pair_ids": sorted(self._pairs),
                "pairing_ids": sorted(self._pairings),
            }

    def _token_digest(self, token: str) -> bytes:
        return hmac.new(
            self._token_pepper,
            token.encode("ascii"),
            hashlib.sha256,
        ).digest()

    def _authenticated_pairing(
        self,
        *,
        pairing_id: str,
        pairing_token: str,
    ) -> PairingRoute:
        try:
            b64url_decode(pairing_id, expected_length=16)
            b64url_decode(pairing_token, expected_length=32)
        except ProtocolViolation:
            raise PairingStateError("unauthorized") from None
        route = self._pairings.get(pairing_id)
        if route is None or not hmac.compare_digest(
            route.pairing_token_digest,
            self._token_digest(pairing_token),
        ):
            raise PairingStateError("unauthorized")
        return route

    def _receiver_pairing(
        self,
        *,
        device_id: str,
        pairing_id: str,
    ) -> PairingRoute:
        try:
            b64url_decode(pairing_id, expected_length=16)
        except ProtocolViolation:
            raise PairingStateError("pairing_not_found") from None
        route = self._pairings.get(pairing_id)
        if route is None or route.device_id != device_id:
            raise PairingStateError("pairing_not_found")
        return route

    @staticmethod
    def _require_active_pairing(
        route: PairingRoute,
        current_time: int,
    ) -> None:
        if route.expires_at < current_time:
            raise PairingStateError("pairing_expired")

    def _prune_pairings(self, current_time: int) -> None:
        stale_before = current_time - 300
        stale_ids = [
            pairing_id
            for pairing_id, route in self._pairings.items()
            if route.expires_at < stale_before
        ]
        for pairing_id in stale_ids:
            del self._pairings[pairing_id]
