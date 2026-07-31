"""Windows DPAPI-protected storage for Phone-to-PC credentials."""

from __future__ import annotations

import base64
import ctypes
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from app_settings import settings_directory
from bridge.protocol import (
    KEY_EPOCH,
    ProtocolViolation,
    b64url_decode,
    b64url_encode,
    normalize_relay_origin,
)


STORE_VERSION = 1
STORE_FILENAME = "phone-to-pc.dat"
CRYPTPROTECT_UI_FORBIDDEN = 0x01
DPAPI_DESCRIPTION = "Webcam QR Scanner Phone-to-PC credentials"
DPAPI_ENTROPY = b"webcam-qr-scanner/wqrs/1/credentials"


class SecureStorageError(RuntimeError):
    """Raised when protected credentials cannot be read or validated."""


class SecretProtector(Protocol):
    def protect(self, plaintext: bytes) -> bytes:
        """Protect bytes for the current operating-system user."""

    def unprotect(self, ciphertext: bytes) -> bytes:
        """Recover bytes previously protected for the current user."""


@dataclass(frozen=True, slots=True)
class RelayDevice:
    relay_origin: str
    device_id: str
    receiver_token: str


@dataclass(frozen=True, slots=True)
class StoredPair:
    relay_origin: str
    device_id: str
    pair_id: str
    root_key: bytes
    phone_label: str
    key_epoch: int = KEY_EPOCH


@dataclass(frozen=True, slots=True)
class PairingStoreSnapshot:
    devices: tuple[RelayDevice, ...] = ()
    pairs: tuple[StoredPair, ...] = ()

    def device_for(self, relay_origin: str) -> RelayDevice | None:
        origin = normalize_relay_origin(relay_origin)
        return next(
            (
                device
                for device in self.devices
                if device.relay_origin == origin
            ),
            None,
        )

    def pairs_for(self, relay_origin: str) -> tuple[StoredPair, ...]:
        origin = normalize_relay_origin(relay_origin)
        return tuple(
            pair for pair in self.pairs if pair.relay_origin == origin
        )


class DpapiProtector:
    """Bind encrypted bytes to the current Windows user with DPAPI."""

    def protect(self, plaintext: bytes) -> bytes:
        if not plaintext:
            raise ValueError("plaintext must not be empty")
        return _dpapi_transform(plaintext, decrypt=False)

    def unprotect(self, ciphertext: bytes) -> bytes:
        if not ciphertext:
            raise SecureStorageError("protected credential file is empty")
        return _dpapi_transform(ciphertext, decrypt=True)


class PairingStore:
    """Atomically persist only DPAPI ciphertext on disk."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        protector: SecretProtector | None = None,
    ) -> None:
        self.path = path or settings_directory() / STORE_FILENAME
        self.protector = protector or DpapiProtector()

    def load(self) -> PairingStoreSnapshot:
        try:
            protected = self.path.read_bytes()
        except FileNotFoundError:
            return PairingStoreSnapshot()
        except OSError as error:
            raise SecureStorageError(
                "protected credential file could not be read"
            ) from error
        try:
            plaintext = self.protector.unprotect(protected)
            value = json.loads(plaintext.decode("utf-8"))
            return _snapshot_from_json(value)
        except (
            OSError,
            UnicodeError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
            ProtocolViolation,
        ) as error:
            raise SecureStorageError(
                "protected credentials are corrupted or unavailable"
            ) from error

    def save(self, snapshot: PairingStoreSnapshot) -> None:
        serialized = _snapshot_to_json(snapshot)
        protected = self.protector.protect(serialized)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.tmp"
        )
        try:
            temporary_path.write_bytes(protected)
            os.replace(temporary_path, self.path)
        except OSError as error:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise SecureStorageError(
                "protected credentials could not be saved"
            ) from error

    def replace_device(
        self,
        device: RelayDevice,
        *,
        clear_pairs: bool,
    ) -> PairingStoreSnapshot:
        current = self.load()
        origin = normalize_relay_origin(device.relay_origin)
        checked_device = _validated_device(device)
        previous = current.device_for(origin)
        if (
            previous is not None
            and previous.device_id != checked_device.device_id
            and current.pairs_for(origin)
            and not clear_pairs
        ):
            raise SecureStorageError(
                "changing a relay device requires clearing its old pairs"
            )
        devices = tuple(
            item for item in current.devices if item.relay_origin != origin
        ) + (checked_device,)
        pairs = (
            tuple(
                pair for pair in current.pairs if pair.relay_origin != origin
            )
            if clear_pairs
            else current.pairs
        )
        updated = PairingStoreSnapshot(devices=devices, pairs=pairs)
        self.save(updated)
        return updated

    def add_pair(self, pair: StoredPair) -> PairingStoreSnapshot:
        current = self.load()
        checked = _validated_pair(pair)
        if not any(
            device.relay_origin == checked.relay_origin
            and device.device_id == checked.device_id
            for device in current.devices
        ):
            raise SecureStorageError(
                "cannot store a pair without its relay device"
            )
        pairs = tuple(
            item
            for item in current.pairs
            if not (
                item.relay_origin == checked.relay_origin
                and item.pair_id == checked.pair_id
            )
        ) + (checked,)
        updated = PairingStoreSnapshot(
            devices=current.devices,
            pairs=pairs,
        )
        self.save(updated)
        return updated


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _dpapi_transform(value: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise OSError("Windows DPAPI is unavailable on this platform")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    input_buffer, input_blob = _blob_from_bytes(value)
    entropy_buffer, entropy_blob = _blob_from_bytes(DPAPI_ENTROPY)
    output_blob = _DataBlob()
    if decrypt:
        function = crypt32.CryptUnprotectData
        function.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_DataBlob),
        ]
        arguments = (
            ctypes.byref(input_blob),
            None,
            ctypes.byref(entropy_blob),
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
    else:
        function = crypt32.CryptProtectData
        function.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.c_wchar_p,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_DataBlob),
        ]
        arguments = (
            ctypes.byref(input_blob),
            DPAPI_DESCRIPTION,
            ctypes.byref(entropy_blob),
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
    function.restype = ctypes.c_bool
    _ = input_buffer, entropy_buffer
    if not function(*arguments):
        error_code = ctypes.get_last_error()
        raise OSError(error_code, "Windows DPAPI operation failed")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree(output_blob.pbData)


def _blob_from_bytes(value: bytes) -> tuple[ctypes.Array[ctypes.c_char], _DataBlob]:
    buffer = ctypes.create_string_buffer(value, len(value))
    pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    return buffer, _DataBlob(len(value), pointer)


def _snapshot_to_json(snapshot: PairingStoreSnapshot) -> bytes:
    devices = [_device_to_mapping(device) for device in snapshot.devices]
    pairs = [_pair_to_mapping(pair) for pair in snapshot.pairs]
    value = {
        "version": STORE_VERSION,
        "devices": sorted(devices, key=lambda item: item["relay_origin"]),
        "pairs": sorted(
            pairs,
            key=lambda item: (item["relay_origin"], item["pair_id"]),
        ),
    }
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _snapshot_from_json(value: object) -> PairingStoreSnapshot:
    if not isinstance(value, dict) or set(value) != {
        "version",
        "devices",
        "pairs",
    }:
        raise ValueError("credential store fields are invalid")
    if value["version"] != STORE_VERSION:
        raise ValueError("credential store version is unsupported")
    if not isinstance(value["devices"], list) or not isinstance(
        value["pairs"],
        list,
    ):
        raise ValueError("credential store collections are invalid")
    devices = tuple(_device_from_mapping(item) for item in value["devices"])
    pairs = tuple(_pair_from_mapping(item) for item in value["pairs"])
    if len({device.relay_origin for device in devices}) != len(devices):
        raise ValueError("credential store contains duplicate devices")
    pair_keys = {(pair.relay_origin, pair.pair_id) for pair in pairs}
    if len(pair_keys) != len(pairs):
        raise ValueError("credential store contains duplicate pairs")
    known_devices = {
        (device.relay_origin, device.device_id) for device in devices
    }
    if any(
        (pair.relay_origin, pair.device_id) not in known_devices
        for pair in pairs
    ):
        raise ValueError("stored pair refers to an unknown relay device")
    return PairingStoreSnapshot(devices=devices, pairs=pairs)


def _device_to_mapping(device: RelayDevice) -> dict[str, object]:
    return asdict(_validated_device(device))


def _pair_to_mapping(pair: StoredPair) -> dict[str, object]:
    checked = _validated_pair(pair)
    return {
        "relay_origin": checked.relay_origin,
        "device_id": checked.device_id,
        "pair_id": checked.pair_id,
        "root_key": b64url_encode(checked.root_key),
        "phone_label": checked.phone_label,
        "key_epoch": checked.key_epoch,
    }


def _device_from_mapping(value: object) -> RelayDevice:
    if not isinstance(value, dict) or set(value) != {
        "relay_origin",
        "device_id",
        "receiver_token",
    }:
        raise ValueError("stored relay device fields are invalid")
    return _validated_device(
        RelayDevice(
            relay_origin=value["relay_origin"],
            device_id=value["device_id"],
            receiver_token=value["receiver_token"],
        )
    )


def _pair_from_mapping(value: object) -> StoredPair:
    if not isinstance(value, dict) or set(value) != {
        "relay_origin",
        "device_id",
        "pair_id",
        "root_key",
        "phone_label",
        "key_epoch",
    }:
        raise ValueError("stored pair fields are invalid")
    return _validated_pair(
        StoredPair(
            relay_origin=value["relay_origin"],
            device_id=value["device_id"],
            pair_id=value["pair_id"],
            root_key=b64url_decode(value["root_key"], expected_length=32),
            phone_label=value["phone_label"],
            key_epoch=value["key_epoch"],
        )
    )


def _validated_device(device: RelayDevice) -> RelayDevice:
    origin = normalize_relay_origin(device.relay_origin)
    b64url_decode(device.device_id, expected_length=16)
    b64url_decode(device.receiver_token, expected_length=32)
    return RelayDevice(
        relay_origin=origin,
        device_id=device.device_id,
        receiver_token=device.receiver_token,
    )


def _validated_pair(pair: StoredPair) -> StoredPair:
    origin = normalize_relay_origin(pair.relay_origin)
    b64url_decode(pair.device_id, expected_length=16)
    b64url_decode(pair.pair_id, expected_length=16)
    if len(pair.root_key) != 32:
        raise ProtocolViolation("stored root key must contain 32 bytes")
    if (
        not isinstance(pair.phone_label, str)
        or not pair.phone_label
        or pair.phone_label != pair.phone_label.strip()
        or len(pair.phone_label) > 80
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in pair.phone_label
        )
    ):
        raise ProtocolViolation("stored phone label is invalid")
    if type(pair.key_epoch) is not int or pair.key_epoch < 1:
        raise ProtocolViolation("stored key epoch is invalid")
    return StoredPair(
        relay_origin=origin,
        device_id=pair.device_id,
        pair_id=pair.pair_id,
        root_key=bytes(pair.root_key),
        phone_label=pair.phone_label,
        key_epoch=pair.key_epoch,
    )
