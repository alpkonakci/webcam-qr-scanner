"""Safe desktop-facing management of securely stored phone pairs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum

from bridge.pairing import (
    RemotePairRevocationStatus,
    revoke_remote_pair,
)
from bridge.protocol import b64url_decode, normalize_relay_origin
from bridge.secure_storage import PairingStore, SecureStorageError, StoredPair


class PairNotStoredError(LookupError):
    """Raised when a requested local pair no longer exists."""


class PairRemovalStatus(Enum):
    """Remote state confirmed before the local pair was removed."""

    REVOKED = "revoked"
    ALREADY_REVOKED = "already_revoked"


@dataclass(frozen=True, slots=True)
class PairedPhoneSummary:
    """Non-secret fields safe to display in the desktop UI."""

    relay_origin: str
    pair_id: str
    short_pair_id: str
    phone_label: str


@dataclass(frozen=True, slots=True)
class PairRemovalResult:
    summary: PairedPhoneSummary
    status: PairRemovalStatus


class PairManagementService:
    """List pairs and revoke them remotely before deleting local secrets."""

    def __init__(self, *, store: PairingStore | None = None) -> None:
        self.store = store or PairingStore()

    def list_pairs(self) -> tuple[PairedPhoneSummary, ...]:
        pairs = self.store.load().pairs
        return tuple(
            _pair_summary(pair)
            for pair in sorted(
                pairs,
                key=lambda item: (
                    item.phone_label.casefold(),
                    item.relay_origin,
                    item.pair_id,
                ),
            )
        )

    def remove_pair(
        self,
        *,
        relay_origin: str,
        pair_id: str,
    ) -> PairRemovalResult:
        """Synchronously revoke and remove a pair for desktop callbacks."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.remove_pair_async(
                    relay_origin=relay_origin,
                    pair_id=pair_id,
                )
            )
        raise RuntimeError(
            "remove_pair cannot run inside an event loop; "
            "await remove_pair_async instead"
        )

    async def remove_pair_async(
        self,
        *,
        relay_origin: str,
        pair_id: str,
    ) -> PairRemovalResult:
        """Revoke at the relay first; retain local secrets on any failure."""

        origin = normalize_relay_origin(relay_origin)
        b64url_decode(pair_id, expected_length=16)
        snapshot = self.store.load()
        pair = next(
            (
                item
                for item in snapshot.pairs
                if item.relay_origin == origin and item.pair_id == pair_id
            ),
            None,
        )
        if pair is None:
            raise PairNotStoredError("paired phone is no longer stored")
        device = snapshot.device_for(origin)
        if device is None or device.device_id != pair.device_id:
            raise SecureStorageError(
                "stored pair does not have a matching relay device"
            )

        remote_status = await revoke_remote_pair(
            relay_origin=origin,
            pair_id=pair_id,
            receiver_token=device.receiver_token,
        )
        self.store.remove_pair(origin, pair_id)
        return PairRemovalResult(
            summary=_pair_summary(pair),
            status=(
                PairRemovalStatus.ALREADY_REVOKED
                if remote_status
                is RemotePairRevocationStatus.ALREADY_REVOKED
                else PairRemovalStatus.REVOKED
            ),
        )


def _pair_summary(pair: StoredPair) -> PairedPhoneSummary:
    short_pair_id = (
        f"{pair.pair_id[:6]}\N{HORIZONTAL ELLIPSIS}{pair.pair_id[-4:]}"
    )
    return PairedPhoneSummary(
        relay_origin=pair.relay_origin,
        pair_id=pair.pair_id,
        short_pair_id=short_pair_id,
        phone_label=pair.phone_label,
    )
