"""Production WQRS/1 cryptographic and validation primitives.

The deterministic values under ``protocol/test-vectors`` are test material.
This module always obtains identifiers, secrets, and nonces from the operating
system cryptographic random-number generator.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


PROTOCOL = "wqrs/1"
KEY_EPOCH = 1
PAIRING_TTL_SECONDS = 120
MESSAGE_TTL_SECONDS = 300
ACK_TTL_SECONDS = 10
MAX_CLOCK_SKEW_SECONDS = 120
MAX_URL_BYTES = 4096
MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991

_BASE64URL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_MESSAGE_FIELDS = frozenset(
    {
        "protocol",
        "type",
        "pair_id",
        "key_epoch",
        "message_id",
        "created_at",
        "expires_at",
        "nonce",
        "ciphertext",
    }
)
_PAIRING_FIELDS = frozenset(
    {
        "protocol",
        "device_id",
        "pairing_id",
        "phone_public_key",
        "expires_at",
        "type",
        "created_at",
        "nonce",
        "ciphertext",
    }
)
_PAIRING_QUERY_FIELDS = frozenset(
    {
        "v",
        "relay",
        "device",
        "pairing",
        "pairing_token",
        "pc_key",
        "secret",
        "expires",
    }
)


class ProtocolViolation(ValueError):
    """Raised when an untrusted WQRS value fails closed validation."""


class AuthenticationFailed(ProtocolViolation):
    """Raised when authenticated decryption detects modified data."""


class ReplayDetected(ProtocolViolation):
    """Raised when a previously accepted message is received again."""


@dataclass(frozen=True, slots=True)
class ReceiverCredentials:
    """Secrets needed by one PC receiver for a single paired phone."""

    device_id: str
    receiver_token: str
    pair_id: str
    root_key: bytes
    key_epoch: int = KEY_EPOCH


@dataclass(frozen=True, slots=True)
class SenderCredentials:
    """Secrets needed by one phone sender for a single paired PC."""

    pair_id: str
    sender_token: str
    root_key: bytes
    key_epoch: int = KEY_EPOCH


@dataclass(frozen=True, slots=True)
class LocalPairing:
    """In-memory credentials produced by a real P-256 pairing derivation."""

    receiver: ReceiverCredentials
    sender: SenderCredentials
    transcript: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PairingQrData:
    """Strictly validated public and secret values carried by the pairing QR."""

    relay_origin: str
    device_id: str
    pairing_id: str
    pairing_token: str
    pc_public_key: bytes
    pairing_secret: bytes
    expires_at: int


@dataclass(frozen=True, slots=True)
class PcPairingSession:
    """Short-lived PC state kept only while one pairing QR is visible."""

    qr: PairingQrData
    receiver_token: str
    private_key: ec.EllipticCurvePrivateKey

    @property
    def pairing_uri(self) -> str:
        return build_pairing_uri(self.qr)


@dataclass(frozen=True, slots=True)
class PhonePairingAttempt:
    """Phone-side ephemeral keys and encrypted request for one QR scan."""

    qr: PairingQrData
    phone_public_key: bytes
    root_key: bytes
    handshake_key: bytes
    request_envelope: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VerifiedPairingRequest:
    """Authenticated phone request plus keys derived independently by the PC."""

    phone_label: str
    platform: str
    phone_public_key: bytes
    root_key: bytes
    handshake_key: bytes


@dataclass(frozen=True, slots=True)
class ApprovedPairing:
    """PC credentials, relay sender token, and encrypted phone result."""

    receiver: ReceiverCredentials
    sender_token: str
    result_envelope: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReceivedUrl:
    """A fully authenticated and locally validated URL message."""

    message_id: str
    url: str
    hostname_ascii: str
    is_secure: bool


def b64url_encode(value: bytes) -> str:
    """Encode bytes as unpadded URL-safe Base64."""

    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def b64url_decode(
    value: object,
    *,
    expected_length: int | None = None,
    minimum_length: int | None = None,
) -> bytes:
    """Strictly decode unpadded URL-safe Base64 with optional size checks."""

    if not isinstance(value, str) or not value or "=" in value:
        raise ProtocolViolation("invalid base64url value")
    if _BASE64URL_PATTERN.fullmatch(value) is None:
        raise ProtocolViolation("invalid base64url alphabet")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as error:
        raise ProtocolViolation("invalid base64url encoding") from error
    if b64url_encode(decoded) != value:
        raise ProtocolViolation("non-canonical base64url encoding")
    if expected_length is not None and len(decoded) != expected_length:
        raise ProtocolViolation("unexpected decoded value length")
    if minimum_length is not None and len(decoded) < minimum_length:
        raise ProtocolViolation("decoded value is too short")
    return decoded


def random_b64url(size: int) -> str:
    """Return a CSPRNG-backed value encoded for WQRS JSON."""

    if size <= 0:
        raise ValueError("random value size must be positive")
    return b64url_encode(secrets.token_bytes(size))


def canonical_json(value: Any) -> bytes:
    """Return the JCS-compatible encoding used by the constrained WQRS schema."""

    _validate_canonical_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validate_canonical_value(value: Any) -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if type(value) is int:
        if not 0 <= value <= MAX_SAFE_JSON_INTEGER:
            raise ProtocolViolation("integer is outside the JSON safe range")
        return
    if isinstance(value, float):
        raise ProtocolViolation("floating-point protocol values are forbidden")
    if isinstance(value, list):
        for item in value:
            _validate_canonical_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key.isascii():
                raise ProtocolViolation("protocol field names must be ASCII")
            _validate_canonical_value(item)
        return
    raise ProtocolViolation(
        f"unsupported protocol value type: {type(value).__name__}"
    )


def hkdf_sha256(ikm: bytes, salt: bytes, info: bytes) -> bytes:
    """Derive one 256-bit purpose-specific WQRS key."""

    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=info,
    ).derive(ikm)


def raw_public_key(private_key: ec.EllipticCurvePrivateKey) -> bytes:
    """Serialize a P-256 public key as an uncompressed SEC1 point."""

    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )


def load_public_key(value: bytes) -> ec.EllipticCurvePublicKey:
    """Load and curve-validate an uncompressed P-256 point."""

    try:
        key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(),
            value,
        )
    except ValueError as error:
        raise ProtocolViolation("invalid P-256 public key") from error
    return key


def normalize_relay_origin(value: str) -> str:
    """Normalize an HTTPS origin, permitting HTTP only on loopback in tests."""

    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").lower()
    is_loopback = hostname in {"127.0.0.1", "::1", "localhost"}
    if parsed.scheme not in {"https", "http"}:
        raise ProtocolViolation("relay origin must use HTTP or HTTPS")
    if parsed.scheme == "http" and not is_loopback:
        raise ProtocolViolation("non-loopback relay origins must use HTTPS")
    if (
        not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ProtocolViolation("relay value must be an origin without a path")
    try:
        port = parsed.port
    except ValueError as error:
        raise ProtocolViolation("invalid relay port") from error
    host_for_origin = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if parsed.scheme == "https" else 80
    port_suffix = "" if port in {None, default_port} else f":{port}"
    return f"{parsed.scheme}://{host_for_origin}{port_suffix}"


def create_pc_pairing_session(
    *,
    relay_origin: str,
    device_id: str,
    receiver_token: str,
    pairing_id: str,
    pairing_token: str,
    expires_at: int,
    now: int | None = None,
) -> PcPairingSession:
    """Create the private PC half of a relay-issued pairing session."""

    current_time = int(time.time()) if now is None else now
    _validate_pairing_expiry(
        expires_at,
        current_time=current_time,
        allow_clock_skew=False,
    )
    b64url_decode(device_id, expected_length=16)
    b64url_decode(receiver_token, expected_length=32)
    b64url_decode(pairing_id, expected_length=16)
    b64url_decode(pairing_token, expected_length=32)
    private_key = ec.generate_private_key(ec.SECP256R1())
    qr = PairingQrData(
        relay_origin=normalize_relay_origin(relay_origin),
        device_id=device_id,
        pairing_id=pairing_id,
        pairing_token=pairing_token,
        pc_public_key=raw_public_key(private_key),
        pairing_secret=secrets.token_bytes(32),
        expires_at=expires_at,
    )
    return PcPairingSession(
        qr=qr,
        receiver_token=receiver_token,
        private_key=private_key,
    )


def build_pairing_uri(qr: PairingQrData) -> str:
    """Serialize one exact, single-value WQRS pairing URI for a QR code."""

    b64url_decode(qr.device_id, expected_length=16)
    b64url_decode(qr.pairing_id, expected_length=16)
    b64url_decode(qr.pairing_token, expected_length=32)
    load_public_key(qr.pc_public_key)
    if len(qr.pairing_secret) != 32:
        raise ProtocolViolation("pairing secret must contain 32 bytes")
    if type(qr.expires_at) is not int or not (
        0 <= qr.expires_at <= MAX_SAFE_JSON_INTEGER
    ):
        raise ProtocolViolation("pairing expiry is invalid")
    parameters = {
        "v": "1",
        "relay": normalize_relay_origin(qr.relay_origin),
        "device": qr.device_id,
        "pairing": qr.pairing_id,
        "pairing_token": qr.pairing_token,
        "pc_key": b64url_encode(qr.pc_public_key),
        "secret": b64url_encode(qr.pairing_secret),
        "expires": str(qr.expires_at),
    }
    return "wqrs://pair?" + urlencode(parameters)


def parse_pairing_uri(
    uri: object,
    *,
    now: int | None = None,
) -> PairingQrData:
    """Parse a pairing QR without accepting duplicates or ambiguous fields."""

    if not isinstance(uri, str) or not uri or uri != uri.strip():
        raise ProtocolViolation("pairing URI must be a non-empty string")
    parsed = urlsplit(uri)
    if (
        parsed.scheme != "wqrs"
        or parsed.netloc != "pair"
        or parsed.path
        or parsed.fragment
    ):
        raise ProtocolViolation("pairing URI target is invalid")
    try:
        pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
        )
    except ValueError as error:
        raise ProtocolViolation("pairing URI query is invalid") from error
    if (
        len(pairs) != len(_PAIRING_QUERY_FIELDS)
        or {key for key, _ in pairs} != _PAIRING_QUERY_FIELDS
    ):
        raise ProtocolViolation(
            "pairing URI must contain each expected field exactly once"
        )
    values = dict(pairs)
    if values["v"] != "1":
        raise ProtocolViolation("pairing URI version is unsupported")
    try:
        expires_at = int(values["expires"])
    except ValueError as error:
        raise ProtocolViolation("pairing expiry is invalid") from error
    if str(expires_at) != values["expires"]:
        raise ProtocolViolation("pairing expiry is not canonical")
    current_time = int(time.time()) if now is None else now
    _validate_pairing_expiry(
        expires_at,
        current_time=current_time,
        allow_clock_skew=True,
    )
    pc_public_key = b64url_decode(values["pc_key"], expected_length=65)
    load_public_key(pc_public_key)
    return PairingQrData(
        relay_origin=normalize_relay_origin(values["relay"]),
        device_id=_validated_b64url(values["device"], 16),
        pairing_id=_validated_b64url(values["pairing"], 16),
        pairing_token=_validated_b64url(values["pairing_token"], 32),
        pc_public_key=pc_public_key,
        pairing_secret=b64url_decode(values["secret"], expected_length=32),
        expires_at=expires_at,
    )


def create_phone_pairing_attempt(
    pairing_uri: str,
    *,
    phone_label: str,
    now: int | None = None,
) -> PhonePairingAttempt:
    """Parse a PC QR and create an authenticated, encrypted phone request."""

    current_time = int(time.time()) if now is None else now
    qr = parse_pairing_uri(pairing_uri, now=current_time)
    clean_label = _validate_device_label(phone_label, field_name="phone label")
    phone_private = ec.generate_private_key(ec.SECP256R1())
    phone_public = raw_public_key(phone_private)
    handshake_key, root_key = _derive_pairing_keys(
        private_key=phone_private,
        peer_public_key=qr.pc_public_key,
        qr=qr,
        phone_public_key=phone_public,
    )
    request_envelope = _build_pairing_envelope(
        qr=qr,
        phone_public_key=phone_public,
        message_type="pair_request",
        handshake_key=handshake_key,
        payload={
            "payload_version": 1,
            "kind": "pair_request",
            "phone_label": clean_label,
            "platform": "pwa",
        },
        now=current_time,
    )
    return PhonePairingAttempt(
        qr=qr,
        phone_public_key=phone_public,
        root_key=root_key,
        handshake_key=handshake_key,
        request_envelope=request_envelope,
    )


def decrypt_pairing_request(
    session: PcPairingSession,
    envelope: object,
    *,
    now: int | None = None,
) -> VerifiedPairingRequest:
    """Authenticate a phone request and independently derive the same keys."""

    checked = _validate_pairing_envelope(
        envelope,
        qr=session.qr,
        expected_type="pair_request",
        now=now,
    )
    phone_public = b64url_decode(
        checked["phone_public_key"],
        expected_length=65,
    )
    handshake_key, root_key = _derive_pairing_keys(
        private_key=session.private_key,
        peer_public_key=phone_public,
        qr=session.qr,
        phone_public_key=phone_public,
    )
    payload = _decrypt_payload(checked, handshake_key)
    if set(payload) != {
        "payload_version",
        "kind",
        "phone_label",
        "platform",
    }:
        raise ProtocolViolation("pairing request has unexpected fields")
    if payload["payload_version"] != 1 or payload["kind"] != "pair_request":
        raise ProtocolViolation("pairing request payload is unsupported")
    if payload["platform"] != "pwa":
        raise ProtocolViolation("pairing client platform is unsupported")
    return VerifiedPairingRequest(
        phone_label=_validate_device_label(
            payload["phone_label"],
            field_name="phone label",
        ),
        platform="pwa",
        phone_public_key=phone_public,
        root_key=root_key,
        handshake_key=handshake_key,
    )


def approve_pairing_request(
    session: PcPairingSession,
    request: VerifiedPairingRequest,
    *,
    pc_label: str,
    now: int | None = None,
) -> ApprovedPairing:
    """Create credentials only after the PC user approves the phone."""

    clean_label = _validate_device_label(pc_label, field_name="PC label")
    pair_id = random_b64url(16)
    sender_token = random_b64url(32)
    result_envelope = _build_pairing_envelope(
        qr=session.qr,
        phone_public_key=request.phone_public_key,
        message_type="pair_result",
        handshake_key=request.handshake_key,
        payload={
            "payload_version": 1,
            "kind": "pair_approved",
            "pair_id": pair_id,
            "sender_token": sender_token,
            "pc_label": clean_label,
            "key_epoch": KEY_EPOCH,
        },
        now=now,
    )
    return ApprovedPairing(
        receiver=ReceiverCredentials(
            device_id=session.qr.device_id,
            receiver_token=session.receiver_token,
            pair_id=pair_id,
            root_key=request.root_key,
        ),
        sender_token=sender_token,
        result_envelope=result_envelope,
    )


def reject_pairing_request(
    session: PcPairingSession,
    request: VerifiedPairingRequest,
    *,
    now: int | None = None,
) -> dict[str, Any]:
    """Return an authenticated rejection without generating pair credentials."""

    return _build_pairing_envelope(
        qr=session.qr,
        phone_public_key=request.phone_public_key,
        message_type="pair_result",
        handshake_key=request.handshake_key,
        payload={
            "payload_version": 1,
            "kind": "pair_rejected",
        },
        now=now,
    )


def decrypt_pairing_result(
    attempt: PhonePairingAttempt,
    envelope: object,
    *,
    now: int | None = None,
) -> SenderCredentials | None:
    """Verify the PC decision; return credentials only for an approval."""

    checked = _validate_pairing_envelope(
        envelope,
        qr=attempt.qr,
        expected_type="pair_result",
        expected_phone_public_key=attempt.phone_public_key,
        now=now,
    )
    payload = _decrypt_payload(checked, attempt.handshake_key)
    if payload == {
        "payload_version": 1,
        "kind": "pair_rejected",
    }:
        return None
    if set(payload) != {
        "payload_version",
        "kind",
        "pair_id",
        "sender_token",
        "pc_label",
        "key_epoch",
    }:
        raise ProtocolViolation("pairing result has unexpected fields")
    if (
        payload["payload_version"] != 1
        or payload["kind"] != "pair_approved"
        or payload["key_epoch"] != KEY_EPOCH
    ):
        raise ProtocolViolation("pairing result payload is unsupported")
    _validate_device_label(payload["pc_label"], field_name="PC label")
    pair_id = _validated_b64url(payload["pair_id"], 16)
    sender_token = _validated_b64url(payload["sender_token"], 32)
    return SenderCredentials(
        pair_id=pair_id,
        sender_token=sender_token,
        root_key=attempt.root_key,
    )


def pairing_transcript(
    qr: PairingQrData,
    phone_public_key: bytes,
) -> dict[str, Any]:
    """Return the canonical fields cryptographically bound during pairing."""

    load_public_key(phone_public_key)
    return {
        "protocol": PROTOCOL,
        "relay_origin": qr.relay_origin,
        "device_id": qr.device_id,
        "pairing_id": qr.pairing_id,
        "expires_at": qr.expires_at,
        "pc_public_key": b64url_encode(qr.pc_public_key),
        "phone_public_key": b64url_encode(phone_public_key),
    }


def create_local_pairing(
    *,
    relay_origin: str,
    device_id: str,
    receiver_token: str,
    now: int | None = None,
) -> LocalPairing:
    """Simulate successful pairing while exercising both sides of ECDH.

    The HTTP pairing user interface belongs to a later slice of Aşama 1. This
    helper provisions only an in-memory local demo; no private key is written
    to disk.
    """

    b64url_decode(device_id, expected_length=16)
    b64url_decode(receiver_token, expected_length=32)
    origin = normalize_relay_origin(relay_origin)
    current_time = int(time.time()) if now is None else now
    pairing_secret = secrets.token_bytes(32)
    pairing_id = random_b64url(16)
    pair_id = random_b64url(16)
    sender_token = random_b64url(32)
    expires_at = current_time + 120

    pc_private = ec.generate_private_key(ec.SECP256R1())
    phone_private = ec.generate_private_key(ec.SECP256R1())
    pc_public = raw_public_key(pc_private)
    phone_public = raw_public_key(phone_private)
    transcript = {
        "protocol": PROTOCOL,
        "relay_origin": origin,
        "device_id": device_id,
        "pairing_id": pairing_id,
        "expires_at": expires_at,
        "pc_public_key": b64url_encode(pc_public),
        "phone_public_key": b64url_encode(phone_public),
    }
    transcript_hash = hashlib.sha256(canonical_json(transcript)).digest()
    pc_shared_secret = pc_private.exchange(
        ec.ECDH(),
        load_public_key(phone_public),
    )
    phone_shared_secret = phone_private.exchange(
        ec.ECDH(),
        load_public_key(pc_public),
    )
    pc_root_key = hkdf_sha256(
        pc_shared_secret,
        pairing_secret,
        b"wqrs/root/v1" + transcript_hash,
    )
    phone_root_key = hkdf_sha256(
        phone_shared_secret,
        pairing_secret,
        b"wqrs/root/v1" + transcript_hash,
    )
    if not secrets.compare_digest(pc_root_key, phone_root_key):
        raise RuntimeError("P-256 pairing produced inconsistent root keys")

    return LocalPairing(
        receiver=ReceiverCredentials(
            device_id=device_id,
            receiver_token=receiver_token,
            pair_id=pair_id,
            root_key=pc_root_key,
        ),
        sender=SenderCredentials(
            pair_id=pair_id,
            sender_token=sender_token,
            root_key=phone_root_key,
        ),
        transcript=transcript,
    )


def validate_url(value: object) -> tuple[str, str, bool]:
    """Validate a decrypted URL and return URL, ASCII host, and HTTPS state."""

    if not isinstance(value, str) or not value:
        raise ProtocolViolation("URL must be a non-empty string")
    if value != value.strip():
        raise ProtocolViolation("URL may not contain surrounding whitespace")
    if len(value.encode("utf-8")) > MAX_URL_BYTES:
        raise ProtocolViolation("URL exceeds the 4096-byte limit")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ProtocolViolation("URL contains a control character")
    if "\\" in value:
        raise ProtocolViolation("URL contains a backslash")

    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ProtocolViolation("only absolute HTTP(S) URLs are accepted")
    if parsed.username is not None or parsed.password is not None:
        raise ProtocolViolation("URL credentials are forbidden")
    try:
        parsed.port
    except ValueError as error:
        raise ProtocolViolation("URL contains an invalid port") from error
    try:
        hostname_ascii = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ProtocolViolation("URL hostname is invalid") from error
    if not hostname_ascii or any(
        ord(character) <= 32 for character in hostname_ascii
    ):
        raise ProtocolViolation("URL hostname is invalid")
    return value, hostname_ascii, scheme == "https"


def build_url_envelope(
    credentials: SenderCredentials,
    url: str,
    *,
    now: int | None = None,
    message_id: str | None = None,
    nonce: bytes | None = None,
) -> dict[str, Any]:
    """Encrypt one URL using a fresh, message-specific key."""

    clean_url, _, _ = validate_url(url)
    created_at = int(time.time()) if now is None else now
    actual_message_id = message_id or random_b64url(16)
    message_id_bytes = b64url_decode(actual_message_id, expected_length=16)
    actual_nonce = secrets.token_bytes(12) if nonce is None else nonce
    if len(actual_nonce) != 12:
        raise ValueError("AES-GCM nonce must contain exactly 12 bytes")
    message_key = hkdf_sha256(
        credentials.root_key,
        message_id_bytes,
        b"wqrs/message-key/v1",
    )
    aad_fields = {
        "protocol": PROTOCOL,
        "type": "url_message",
        "pair_id": credentials.pair_id,
        "key_epoch": credentials.key_epoch,
        "message_id": actual_message_id,
        "created_at": created_at,
        "expires_at": created_at + MESSAGE_TTL_SECONDS,
        "nonce": b64url_encode(actual_nonce),
    }
    payload = {
        "payload_version": 1,
        "kind": "url",
        "url": clean_url,
    }
    ciphertext = AESGCM(message_key).encrypt(
        actual_nonce,
        canonical_json(payload),
        canonical_json(aad_fields),
    )
    return {**aad_fields, "ciphertext": b64url_encode(ciphertext)}


def decrypt_url_envelope(
    credentials: ReceiverCredentials,
    envelope: object,
    *,
    replay_guard: Any,
    now: int | None = None,
) -> ReceivedUrl:
    """Authenticate, decrypt, validate, and replay-record one URL envelope."""

    checked = _validate_message_envelope(
        envelope,
        expected_type="url_message",
        expected_pair_id=credentials.pair_id,
        expected_key_epoch=credentials.key_epoch,
        maximum_ttl=MESSAGE_TTL_SECONDS,
        now=now,
    )
    message_id_bytes = b64url_decode(
        checked["message_id"],
        expected_length=16,
    )
    message_key = hkdf_sha256(
        credentials.root_key,
        message_id_bytes,
        b"wqrs/message-key/v1",
    )
    payload = _decrypt_payload(checked, message_key)
    if set(payload) != {"payload_version", "kind", "url"}:
        raise ProtocolViolation("URL payload has unexpected fields")
    if payload["payload_version"] != 1 or payload["kind"] != "url":
        raise ProtocolViolation("unsupported URL payload")
    url, hostname_ascii, is_secure = validate_url(payload["url"])
    replay_guard.remember(
        message_id_bytes,
        expires_at=checked["expires_at"],
        now=int(time.time()) if now is None else now,
    )
    return ReceivedUrl(
        message_id=checked["message_id"],
        url=url,
        hostname_ascii=hostname_ascii,
        is_secure=is_secure,
    )


def build_delivery_ack(
    credentials: ReceiverCredentials,
    message_id: str,
    *,
    now: int | None = None,
) -> dict[str, Any]:
    """Build an encrypted acknowledgement after successful PC validation."""

    message_id_bytes = b64url_decode(message_id, expected_length=16)
    created_at = int(time.time()) if now is None else now
    nonce = secrets.token_bytes(12)
    ack_key = hkdf_sha256(
        credentials.root_key,
        message_id_bytes,
        b"wqrs/ack-key/v1",
    )
    aad_fields = {
        "protocol": PROTOCOL,
        "type": "delivered_ack",
        "pair_id": credentials.pair_id,
        "key_epoch": credentials.key_epoch,
        "message_id": message_id,
        "created_at": created_at,
        "expires_at": created_at + ACK_TTL_SECONDS,
        "nonce": b64url_encode(nonce),
    }
    payload = {
        "payload_version": 1,
        "kind": "delivered",
        "message_id": message_id,
    }
    ciphertext = AESGCM(ack_key).encrypt(
        nonce,
        canonical_json(payload),
        canonical_json(aad_fields),
    )
    return {**aad_fields, "ciphertext": b64url_encode(ciphertext)}


def verify_delivery_ack(
    credentials: SenderCredentials,
    envelope: object,
    *,
    expected_message_id: str,
    now: int | None = None,
) -> None:
    """Verify that the paired PC, rather than the relay, created the ACK."""

    checked = _validate_message_envelope(
        envelope,
        expected_type="delivered_ack",
        expected_pair_id=credentials.pair_id,
        expected_key_epoch=credentials.key_epoch,
        maximum_ttl=ACK_TTL_SECONDS,
        now=now,
    )
    if not secrets.compare_digest(
        checked["message_id"],
        expected_message_id,
    ):
        raise ProtocolViolation("ACK belongs to a different message")
    message_id_bytes = b64url_decode(
        checked["message_id"],
        expected_length=16,
    )
    ack_key = hkdf_sha256(
        credentials.root_key,
        message_id_bytes,
        b"wqrs/ack-key/v1",
    )
    payload = _decrypt_payload(checked, ack_key)
    if set(payload) != {"payload_version", "kind", "message_id"}:
        raise ProtocolViolation("ACK payload has unexpected fields")
    if (
        payload["payload_version"] != 1
        or payload["kind"] != "delivered"
        or payload["message_id"] != expected_message_id
    ):
        raise ProtocolViolation("invalid delivered ACK payload")


def _validate_message_envelope(
    envelope: object,
    *,
    expected_type: str,
    expected_pair_id: str,
    expected_key_epoch: int,
    maximum_ttl: int,
    now: int | None,
) -> dict[str, Any]:
    if not isinstance(envelope, dict) or set(envelope) != _MESSAGE_FIELDS:
        raise ProtocolViolation("message envelope fields are invalid")
    if envelope["protocol"] != PROTOCOL or envelope["type"] != expected_type:
        raise ProtocolViolation("unsupported protocol message type")
    if (
        not isinstance(envelope["pair_id"], str)
        or not secrets.compare_digest(envelope["pair_id"], expected_pair_id)
    ):
        raise ProtocolViolation("message belongs to another pair")
    if type(envelope["key_epoch"]) is not int:
        raise ProtocolViolation("key epoch must be an integer")
    if envelope["key_epoch"] != expected_key_epoch:
        raise ProtocolViolation("unsupported key epoch")
    b64url_decode(envelope["pair_id"], expected_length=16)
    b64url_decode(envelope["message_id"], expected_length=16)
    b64url_decode(envelope["nonce"], expected_length=12)
    b64url_decode(envelope["ciphertext"], minimum_length=16)

    created_at = envelope["created_at"]
    expires_at = envelope["expires_at"]
    if type(created_at) is not int or type(expires_at) is not int:
        raise ProtocolViolation("message timestamps must be integers")
    if not (
        0 <= created_at <= MAX_SAFE_JSON_INTEGER
        and 0 <= expires_at <= MAX_SAFE_JSON_INTEGER
    ):
        raise ProtocolViolation("message timestamp is outside the safe range")
    if expires_at < created_at or expires_at - created_at > maximum_ttl:
        raise ProtocolViolation("message lifetime is invalid")
    current_time = int(time.time()) if now is None else now
    if created_at > current_time + MAX_CLOCK_SKEW_SECONDS:
        raise ProtocolViolation("message was created too far in the future")
    if expires_at < current_time:
        raise ProtocolViolation("message has expired")
    return envelope


def _decrypt_payload(
    envelope: dict[str, Any],
    key: bytes,
) -> dict[str, Any]:
    aad_fields = {
        field: value
        for field, value in envelope.items()
        if field != "ciphertext"
    }
    try:
        plaintext = AESGCM(key).decrypt(
            b64url_decode(envelope["nonce"], expected_length=12),
            b64url_decode(envelope["ciphertext"], minimum_length=16),
            canonical_json(aad_fields),
        )
    except InvalidTag as error:
        raise AuthenticationFailed("message authentication failed") from error
    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProtocolViolation("decrypted payload is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ProtocolViolation("decrypted payload must be an object")
    if canonical_json(payload) != plaintext:
        raise ProtocolViolation("decrypted payload is not canonical JSON")
    return payload


def _build_pairing_envelope(
    *,
    qr: PairingQrData,
    phone_public_key: bytes,
    message_type: str,
    handshake_key: bytes,
    payload: dict[str, Any],
    now: int | None,
) -> dict[str, Any]:
    if message_type not in {"pair_request", "pair_result"}:
        raise ValueError("unsupported pairing message type")
    current_time = int(time.time()) if now is None else now
    if current_time > qr.expires_at:
        raise ProtocolViolation("pairing session has expired")
    load_public_key(phone_public_key)
    nonce = secrets.token_bytes(12)
    aad_fields = {
        "protocol": PROTOCOL,
        "device_id": qr.device_id,
        "pairing_id": qr.pairing_id,
        "phone_public_key": b64url_encode(phone_public_key),
        "expires_at": qr.expires_at,
        "type": message_type,
        "created_at": current_time,
        "nonce": b64url_encode(nonce),
    }
    ciphertext = AESGCM(handshake_key).encrypt(
        nonce,
        canonical_json(payload),
        canonical_json(aad_fields),
    )
    return {**aad_fields, "ciphertext": b64url_encode(ciphertext)}


def _validate_pairing_envelope(
    envelope: object,
    *,
    qr: PairingQrData,
    expected_type: str,
    expected_phone_public_key: bytes | None = None,
    now: int | None,
) -> dict[str, Any]:
    if not isinstance(envelope, dict) or set(envelope) != _PAIRING_FIELDS:
        raise ProtocolViolation("pairing envelope fields are invalid")
    if envelope["protocol"] != PROTOCOL or envelope["type"] != expected_type:
        raise ProtocolViolation("pairing message type is unsupported")
    if (
        not isinstance(envelope["device_id"], str)
        or not secrets.compare_digest(envelope["device_id"], qr.device_id)
        or not isinstance(envelope["pairing_id"], str)
        or not secrets.compare_digest(envelope["pairing_id"], qr.pairing_id)
    ):
        raise ProtocolViolation("pairing message belongs to another session")
    phone_public = b64url_decode(
        envelope["phone_public_key"],
        expected_length=65,
    )
    load_public_key(phone_public)
    if expected_phone_public_key is not None and not secrets.compare_digest(
        phone_public,
        expected_phone_public_key,
    ):
        raise ProtocolViolation("pairing result belongs to another phone")
    b64url_decode(envelope["nonce"], expected_length=12)
    b64url_decode(envelope["ciphertext"], minimum_length=16)
    created_at = envelope["created_at"]
    expires_at = envelope["expires_at"]
    if type(created_at) is not int or type(expires_at) is not int:
        raise ProtocolViolation("pairing timestamps must be integers")
    if expires_at != qr.expires_at:
        raise ProtocolViolation("pairing expiry does not match the QR")
    current_time = int(time.time()) if now is None else now
    if created_at > current_time + MAX_CLOCK_SKEW_SECONDS:
        raise ProtocolViolation("pairing message was created too far in the future")
    if created_at > expires_at or expires_at < current_time:
        raise ProtocolViolation("pairing session has expired")
    return envelope


def _derive_pairing_keys(
    *,
    private_key: ec.EllipticCurvePrivateKey,
    peer_public_key: bytes,
    qr: PairingQrData,
    phone_public_key: bytes,
) -> tuple[bytes, bytes]:
    transcript = pairing_transcript(qr, phone_public_key)
    transcript_hash = hashlib.sha256(canonical_json(transcript)).digest()
    shared_secret = private_key.exchange(
        ec.ECDH(),
        load_public_key(peer_public_key),
    )
    return (
        hkdf_sha256(
            shared_secret,
            qr.pairing_secret,
            b"wqrs/handshake/v1" + transcript_hash,
        ),
        hkdf_sha256(
            shared_secret,
            qr.pairing_secret,
            b"wqrs/root/v1" + transcript_hash,
        ),
    )


def _validate_pairing_expiry(
    expires_at: object,
    *,
    current_time: int,
    allow_clock_skew: bool,
) -> None:
    if type(expires_at) is not int or not (
        0 <= expires_at <= MAX_SAFE_JSON_INTEGER
    ):
        raise ProtocolViolation("pairing expiry is invalid")
    if expires_at < current_time:
        raise ProtocolViolation("pairing session has expired")
    allowed_lifetime = PAIRING_TTL_SECONDS
    if allow_clock_skew:
        allowed_lifetime += MAX_CLOCK_SKEW_SECONDS
    if expires_at - current_time > allowed_lifetime:
        raise ProtocolViolation("pairing session lifetime is too long")


def _validate_device_label(value: object, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 80
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ProtocolViolation(f"{field_name} is invalid")
    return value


def _validated_b64url(value: object, size: int) -> str:
    b64url_decode(value, expected_length=size)
    assert isinstance(value, str)
    return value
