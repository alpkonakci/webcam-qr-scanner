"""Credential-free, expiring receiver health for desktop child windows."""
from __future__ import annotations
import json
import os
from pathlib import Path
import threading
import time
from app_settings import settings_directory

_lock = threading.Lock()
FRESH_SECONDS = 75


def status_path() -> Path:
    return settings_directory() / "receiver-status.json"


def record_connection(origin: str, reachable: bool, *, path: Path | None = None, now: float | None = None) -> None:
    target = path or status_path()
    with _lock:
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(data, dict): data = {}
        except (OSError, ValueError): data = {}
        data[origin] = {"reachable": bool(reachable), "checked_at": time.time() if now is None else now}
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(data), encoding="utf-8")
        temporary.replace(target)


def connection_confirmed(origin: str, *, path: Path | None = None, now: float | None = None) -> bool:
    try:
        item = json.loads((path or status_path()).read_text(encoding="utf-8"))[origin]
        age = (time.time() if now is None else now) - item["checked_at"]
        return item["reachable"] is True and 0 <= age < FRESH_SECONDS
    except (OSError, ValueError, TypeError, KeyError):
        return False
