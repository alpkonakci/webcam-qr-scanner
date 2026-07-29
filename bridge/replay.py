"""Digest-only replay protection for WQRS messages."""

from __future__ import annotations

import hashlib
import threading
import time

from bridge.protocol import ReplayDetected


class InMemoryReplayGuard:
    """Remember accepted message-ID digests without retaining URL data."""

    def __init__(self) -> None:
        self._expirations: dict[bytes, int] = {}
        self._lock = threading.Lock()

    def remember(
        self,
        message_id: bytes,
        *,
        expires_at: int,
        now: int | None = None,
    ) -> None:
        current_time = int(time.time()) if now is None else now
        digest = hashlib.sha256(message_id).digest()
        with self._lock:
            self._prune(current_time)
            if digest in self._expirations:
                raise ReplayDetected("message has already been accepted")
            self._expirations[digest] = expires_at

    def __len__(self) -> int:
        with self._lock:
            return len(self._expirations)

    def _prune(self, now: int) -> None:
        expired = [
            digest
            for digest, expires_at in self._expirations.items()
            if expires_at < now
        ]
        for digest in expired:
            del self._expirations[digest]

