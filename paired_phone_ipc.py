"""Small, credential-free requests for the paired-phone GUI child process."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from app_settings import settings_directory


PAIRED_PHONES_SNAPSHOT_FILENAME = "paired-phones-view.json"
REMOVE_PHONE_REQUEST_FILENAME = "remove-phone-access.request"
MAX_PAIRED_PHONES = 100


@dataclass(frozen=True, slots=True)
class PairedPhoneView:
    """Non-secret fields required to render and identify one paired phone."""

    relay_origin: str
    pair_id: str
    phone_label: str


@dataclass(frozen=True, slots=True)
class RemovePhoneRequest:
    """Locator selected by the GUI; relay credentials are never included."""

    relay_origin: str
    pair_id: str
    phone_label: str


def write_paired_phones_snapshot(
    phones: tuple[PairedPhoneView, ...],
    directory: Path | None = None,
) -> None:
    """Atomically publish a one-use, non-secret view for the GUI child."""

    checked = tuple(_validated_phone(phone) for phone in phones)
    if len(checked) > MAX_PAIRED_PHONES:
        raise ValueError("too many paired phones")
    _write_json(
        PAIRED_PHONES_SNAPSHOT_FILENAME,
        [asdict(phone) for phone in checked],
        directory,
    )


def consume_paired_phones_snapshot(
    directory: Path | None = None,
) -> tuple[PairedPhoneView, ...]:
    """Consume the latest GUI snapshot, returning an empty view if invalid."""

    value = _consume_json(PAIRED_PHONES_SNAPSHOT_FILENAME, directory)
    if not isinstance(value, list) or len(value) > MAX_PAIRED_PHONES:
        return ()
    try:
        return tuple(_phone_from_mapping(item) for item in value)
    except (TypeError, ValueError):
        return ()


def request_phone_removal(
    phone: PairedPhoneView,
    directory: Path | None = None,
) -> None:
    """Publish the selected pair locator without any receiver credentials."""

    checked = _validated_phone(phone)
    _write_json(
        REMOVE_PHONE_REQUEST_FILENAME,
        asdict(
            RemovePhoneRequest(
                relay_origin=checked.relay_origin,
                pair_id=checked.pair_id,
                phone_label=checked.phone_label,
            )
        ),
        directory,
    )


def consume_phone_removal_request(
    directory: Path | None = None,
) -> RemovePhoneRequest | None:
    """Consume one removal request, rejecting malformed or extra fields."""

    value = _consume_json(REMOVE_PHONE_REQUEST_FILENAME, directory)
    if not isinstance(value, dict) or set(value) != {
        "relay_origin",
        "pair_id",
        "phone_label",
    }:
        return None
    try:
        checked = _validated_phone(
            PairedPhoneView(
                relay_origin=value["relay_origin"],
                pair_id=value["pair_id"],
                phone_label=value["phone_label"],
            )
        )
    except (TypeError, ValueError):
        return None
    return RemovePhoneRequest(
        relay_origin=checked.relay_origin,
        pair_id=checked.pair_id,
        phone_label=checked.phone_label,
    )


def clear_paired_phone_requests(directory: Path | None = None) -> None:
    """Remove stale one-use process messages at controller startup."""

    for filename in (
        PAIRED_PHONES_SNAPSHOT_FILENAME,
        REMOVE_PHONE_REQUEST_FILENAME,
    ):
        try:
            _path(filename, directory).unlink()
        except (FileNotFoundError, OSError):
            pass


def _path(filename: str, directory: Path | None) -> Path:
    return (directory or settings_directory()) / filename


def _write_json(
    filename: str,
    value: object,
    directory: Path | None,
) -> None:
    path = _path(filename, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _consume_json(filename: str, directory: Path | None) -> object | None:
    path = _path(filename, directory)
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeError):
        return None
    finally:
        try:
            path.unlink()
        except (FileNotFoundError, OSError):
            pass
    try:
        return json.loads(text)
    except (UnboundLocalError, json.JSONDecodeError):
        return None


def _phone_from_mapping(value: object) -> PairedPhoneView:
    if not isinstance(value, dict) or set(value) != {
        "relay_origin",
        "pair_id",
        "phone_label",
    }:
        raise ValueError("paired-phone view fields are invalid")
    return _validated_phone(
        PairedPhoneView(
            relay_origin=value["relay_origin"],
            pair_id=value["pair_id"],
            phone_label=value["phone_label"],
        )
    )


def _validated_phone(phone: PairedPhoneView) -> PairedPhoneView:
    if (
        not isinstance(phone.relay_origin, str)
        or not phone.relay_origin.startswith(("https://", "http://"))
        or len(phone.relay_origin) > 2048
        or any(character.isspace() for character in phone.relay_origin)
    ):
        raise ValueError("relay origin is invalid")
    if (
        not isinstance(phone.pair_id, str)
        or not 8 <= len(phone.pair_id) <= 128
        or any(
            not (character.isascii() and (character.isalnum() or character in "-_"))
            for character in phone.pair_id
        )
    ):
        raise ValueError("pair identifier is invalid")
    if (
        not isinstance(phone.phone_label, str)
        or not phone.phone_label
        or phone.phone_label != phone.phone_label.strip()
        or len(phone.phone_label) > 80
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in phone.phone_label
        )
    ):
        raise ValueError("phone label is invalid")
    return phone
