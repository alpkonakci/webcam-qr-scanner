"""Small local control signals between independently launched app modes."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

from app_settings import settings_directory


EXIT_REQUEST_FILENAME = "bridge-exit.request"
OPEN_CAMERA_REQUEST_FILENAME = "open-camera.request"
CAMERA_CLOSED_FILENAME = "camera-closed.request"


def _signal_path(filename: str, directory: Path | None = None) -> Path:
    base_directory = directory or settings_directory()
    return base_directory / filename


def _request(
    filename: str,
    directory: Path | None = None,
    *,
    content: str | None = None,
) -> None:
    path = _signal_path(filename, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary_path.write_text(
        str(os.getpid()) if content is None else content,
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def _consume(filename: str, directory: Path | None = None) -> bool:
    path = _signal_path(filename, directory)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def _consume_content(
    filename: str,
    directory: Path | None = None,
) -> str | None:
    path = _signal_path(filename, directory)
    try:
        content = path.read_text(encoding="utf-8")
        path.unlink()
        return content
    except (FileNotFoundError, OSError, UnicodeError):
        return None


def request_bridge_exit(directory: Path | None = None) -> None:
    _request(EXIT_REQUEST_FILENAME, directory)


def consume_bridge_exit_request(directory: Path | None = None) -> bool:
    return _consume(EXIT_REQUEST_FILENAME, directory)


def request_open_camera(
    arguments: Sequence[str] = (),
    directory: Path | None = None,
) -> None:
    content = json.dumps(list(arguments), ensure_ascii=False)
    _request(OPEN_CAMERA_REQUEST_FILENAME, directory, content=content)


def consume_open_camera_request(
    directory: Path | None = None,
) -> list[str] | None:
    content = _consume_content(OPEN_CAMERA_REQUEST_FILENAME, directory)
    if content is None:
        return None
    try:
        arguments = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(arguments, list):
        return None
    if any(not isinstance(argument, str) for argument in arguments):
        return None
    return arguments


def request_camera_closed(directory: Path | None = None) -> None:
    _request(CAMERA_CLOSED_FILENAME, directory)


def consume_camera_closed(directory: Path | None = None) -> bool:
    return _consume(CAMERA_CLOSED_FILENAME, directory)


def clear_control_requests(directory: Path | None = None) -> None:
    for filename in (
        EXIT_REQUEST_FILENAME,
        OPEN_CAMERA_REQUEST_FILENAME,
        CAMERA_CLOSED_FILENAME,
    ):
        _consume(filename, directory)
