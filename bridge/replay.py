"""Digest-only replay protection for WQRS messages."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

from bridge.protocol import MESSAGE_TTL_SECONDS, MAX_CLOCK_SKEW_SECONDS, ReplayDetected
from bridge.secure_storage import DpapiProtector, SecretProtector, SecureStorageError


REPLAY_FILENAME = "message-replay.sqlite3"
MAX_REPLAY_RECORDS = 8192
MAX_PROTECTED_BYTES = 2 * 1024 * 1024


class PersistentReplayGuard:
    """Atomic, current-user protected ledger containing only scoped ID digests.

    SQLite serializes transactions across threads/processes. The entire ledger
    payload is DPAPI ciphertext, including its expiries; no URL, token or key
    is written to this database. Storage errors never fall back to memory.
    """

    def __init__(
        self, path: Path, *, scope: str, protector: SecretProtector | None = None,
    ) -> None:
        if not scope or len(scope.encode("utf-8")) > 4096:
            raise ValueError("invalid replay scope")
        self.path = path
        self.scope = scope.encode("utf-8")
        self.protector = protector if protector is not None else DpapiProtector()

    def remember(self, message_id: bytes, *, expires_at: int, now: int | None = None) -> None:
        current_time = int(time.time()) if now is None else now
        if (
            not isinstance(message_id, bytes) or len(message_id) != 16
            or type(current_time) is not int or current_time < 0
            or type(expires_at) is not int or expires_at < current_time
            or expires_at > current_time + MESSAGE_TTL_SECONDS + MAX_CLOCK_SKEW_SECONDS
        ):
            raise SecureStorageError("invalid replay record")
        digest = hashlib.sha256(self.scope + b"\0" + message_id).hexdigest()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            existed = self.path.exists()
            with closing(sqlite3.connect(self.path, timeout=5, isolation_level=None)) as db:
                db.execute("PRAGMA secure_delete=ON")
                db.execute("BEGIN IMMEDIATE")
                try:
                    table = db.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='replay_state'"
                    ).fetchone()
                    if table is None:
                        if existed:
                            raise SecureStorageError("replay ledger schema is missing")
                        db.execute("CREATE TABLE replay_state (id INTEGER PRIMARY KEY CHECK(id=1), payload BLOB NOT NULL)")
                        entries: dict[str, int] = {}
                    else:
                        row = db.execute("SELECT payload FROM replay_state WHERE id=1").fetchone()
                        if row is None or not isinstance(row[0], bytes) or len(row[0]) > MAX_PROTECTED_BYTES:
                            raise SecureStorageError("replay ledger payload is invalid")
                        value = json.loads(self.protector.unprotect(row[0]).decode("utf-8"))
                        if (
                            not isinstance(value, dict) or set(value) != {"version", "kind", "entries"}
                            or type(value["version"]) is not int or value["version"] != 1
                            or value["kind"] != "wqrs-replay" or not isinstance(value["entries"], dict)
                        ):
                            raise SecureStorageError("replay ledger format is invalid")
                        entries = value["entries"]
                        if len(entries) > MAX_REPLAY_RECORDS or any(
                            not isinstance(key, str) or re.fullmatch(r"[0-9a-f]{64}", key) is None
                            or type(expiry) is not int or not 0 <= expiry <= 2**53 - 1
                            for key, expiry in entries.items()
                        ):
                            raise SecureStorageError("replay ledger records are invalid")
                    entries = {key: expiry for key, expiry in entries.items() if expiry >= current_time}
                    if digest in entries:
                        raise ReplayDetected("message has already been accepted")
                    if len(entries) >= MAX_REPLAY_RECORDS:
                        raise SecureStorageError("replay ledger is full")
                    entries[digest] = expires_at
                    serialized = json.dumps(
                        {"version": 1, "kind": "wqrs-replay", "entries": entries},
                        separators=(",", ":"), sort_keys=True,
                    ).encode("utf-8")
                    protected = self.protector.protect(serialized)
                    if not protected or len(protected) > MAX_PROTECTED_BYTES:
                        raise SecureStorageError("replay ledger protection failed")
                    db.execute("INSERT OR REPLACE INTO replay_state (id, payload) VALUES (1, ?)", (protected,))
                    db.execute("COMMIT")
                except BaseException:
                    db.execute("ROLLBACK")
                    raise
        except ReplayDetected:
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError) as error:
            raise SecureStorageError("replay protection is unavailable") from error


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
