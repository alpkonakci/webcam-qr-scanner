"""Persistent per-user settings for the desktop application."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


SETTINGS_VERSION = 1
APPLICATION_DIRECTORY = "Webcam QR Scanner"
SETTINGS_FILENAME = "settings.json"


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Small user-experience preferences that are safe to persist locally."""

    version: int = SETTINGS_VERSION
    camera_closed_notice_shown: bool = False


def settings_directory(environment: dict[str, str] | None = None) -> Path:
    """Return the per-user application data directory."""

    environment = os.environ if environment is None else environment
    local_app_data = environment.get("LOCALAPPDATA")
    base_directory = (
        Path(local_app_data)
        if local_app_data
        else Path.home() / "AppData" / "Local"
    )
    return base_directory / APPLICATION_DIRECTORY


def settings_path(environment: dict[str, str] | None = None) -> Path:
    return settings_directory(environment) / SETTINGS_FILENAME


class SettingsStore:
    """Load and atomically replace the small application settings file."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings_path()

    def load(self) -> AppSettings:
        try:
            raw_value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw_value, dict):
                return AppSettings()
            return _settings_from_mapping(raw_value)
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.tmp"
        )
        serialized = json.dumps(asdict(settings), indent=2, sort_keys=True) + "\n"
        temporary_path.write_text(serialized, encoding="utf-8", newline="\n")
        os.replace(temporary_path, self.path)

    def update(self, **changes: bool | int) -> AppSettings:
        current = self.load()
        updated = replace(current, **changes)
        self.save(updated)
        return updated


def _settings_from_mapping(value: dict[str, Any]) -> AppSettings:
    """Accept known fields only and fail safely on malformed values."""

    version = value.get("version", SETTINGS_VERSION)
    if type(version) is not int or version != SETTINGS_VERSION:
        return AppSettings()

    boolean_fields = ("camera_closed_notice_shown",)
    if any(type(value.get(field, False)) is not bool for field in boolean_fields):
        return AppSettings()

    return AppSettings(
        version=version,
        camera_closed_notice_shown=value.get(
            "camera_closed_notice_shown",
            False,
        ),
    )
