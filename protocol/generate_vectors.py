"""Generate deterministic WQRS/1 cross-language conformance vectors.

The fixed secrets in this module are public test material. They must never be
used by the application or copied into production code.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


PROTOCOL = "wqrs/1"
VECTOR_VERSION = 1
OUTPUT_PATH = Path(__file__).with_name("test-vectors") / "wqrs-1.json"
MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991


def b64url_encode(value: bytes) -> str:
    """Encode bytes using URL-safe Base64 without padding."""

    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def canonical_json(value: Any) -> bytes:
    """Return the JCS-compatible encoding for WQRS protocol values.

    WQRS property names are ASCII and numeric fields are safe-range integers.
    Floats are forbidden, avoiding language-specific number formatting.
    """

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
    if isinstance(value, int):
        if not 0 <= value <= MAX_SAFE_JSON_INTEGER:
            raise ValueError("protocol integers must be non-negative JSON-safe values")
        return
    if isinstance(value, float):
        raise TypeError("floating-point numbers are forbidden in WQRS canonical JSON")
    if isinstance(value, list):
        for item in value:
            _validate_canonical_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key.isascii():
                raise TypeError("WQRS property names must be ASCII strings")
            _validate_canonical_value(item)
        return
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def hkdf_sha256(ikm: bytes, salt: bytes, info: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=info,
    ).derive(ikm)


def raw_public_key(private_key: ec.EllipticCurvePrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )


def encrypted_case(
    *,
    key: bytes,
    nonce: bytes,
    aad_fields: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    aad = canonical_json(aad_fields)
    plaintext = canonical_json(payload)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    return {
        "payload": payload,
        "payload_jcs": plaintext.decode("utf-8"),
        "aad_jcs": aad.decode("utf-8"),
        "envelope": {
            **aad_fields,
            "ciphertext": b64url_encode(ciphertext),
        },
    }


def build_vector() -> dict[str, Any]:
    """Build the single deterministic WQRS/1 vector."""

    pc_private_bytes = bytes(range(1, 33))
    phone_private_bytes = bytes(range(33, 65))
    pairing_secret = bytes(range(65, 97))
    pairing_relay_token = bytes(range(97, 129))
    sender_token = bytes(range(129, 161))

    device_id = bytes.fromhex("00112233445566778899aabbccddeeff")
    pairing_id = bytes.fromhex("102132435465768798a9babbdcddedef")
    pair_id = bytes.fromhex("2031425364758697a8b9cadbecfd0e1f")
    message_id = bytes.fromhex("30415263748596a7b8c9daebfc0d1e2f")

    pair_request_nonce = bytes.fromhex("000102030405060708090a0b")
    pair_result_nonce = bytes.fromhex("101112131415161718191a1b")
    message_nonce = bytes.fromhex("202122232425262728292a2b")
    ack_nonce = bytes.fromhex("303132333435363738393a3b")

    pairing_expires_at = 1_785_100_000
    pair_request_created_at = pairing_expires_at - 90
    pair_result_created_at = pairing_expires_at - 60
    message_created_at = pairing_expires_at + 100
    message_expires_at = message_created_at + 300
    ack_created_at = message_created_at + 1
    ack_expires_at = ack_created_at + 10
    key_epoch = 1

    pc_private = ec.derive_private_key(
        int.from_bytes(pc_private_bytes, "big"),
        ec.SECP256R1(),
    )
    phone_private = ec.derive_private_key(
        int.from_bytes(phone_private_bytes, "big"),
        ec.SECP256R1(),
    )
    pc_public_bytes = raw_public_key(pc_private)
    phone_public_bytes = raw_public_key(phone_private)
    shared_secret = phone_private.exchange(ec.ECDH(), pc_private.public_key())

    transcript = {
        "protocol": PROTOCOL,
        "relay_origin": "https://relay.example",
        "device_id": b64url_encode(device_id),
        "pairing_id": b64url_encode(pairing_id),
        "expires_at": pairing_expires_at,
        "pc_public_key": b64url_encode(pc_public_bytes),
        "phone_public_key": b64url_encode(phone_public_bytes),
    }
    transcript_jcs = canonical_json(transcript)
    transcript_hash = hashlib.sha256(transcript_jcs).digest()
    pairing_uri = "wqrs://pair?" + urlencode(
        {
            "v": "1",
            "relay": transcript["relay_origin"],
            "device": transcript["device_id"],
            "pairing": transcript["pairing_id"],
            "pairing_token": b64url_encode(pairing_relay_token),
            "pc_key": transcript["pc_public_key"],
            "secret": b64url_encode(pairing_secret),
            "expires": str(pairing_expires_at),
        }
    )
    handshake_key = hkdf_sha256(
        shared_secret,
        pairing_secret,
        b"wqrs/handshake/v1" + transcript_hash,
    )
    root_key = hkdf_sha256(
        shared_secret,
        pairing_secret,
        b"wqrs/root/v1" + transcript_hash,
    )

    pairing_aad_base = {
        "protocol": PROTOCOL,
        "device_id": b64url_encode(device_id),
        "pairing_id": b64url_encode(pairing_id),
        "phone_public_key": b64url_encode(phone_public_bytes),
        "expires_at": pairing_expires_at,
    }
    pair_request = encrypted_case(
        key=handshake_key,
        nonce=pair_request_nonce,
        aad_fields={
            **pairing_aad_base,
            "type": "pair_request",
            "created_at": pair_request_created_at,
            "nonce": b64url_encode(pair_request_nonce),
        },
        payload={
            "payload_version": 1,
            "kind": "pair_request",
            "phone_label": "Test Mobile Browser",
            "platform": "pwa",
        },
    )
    pair_result = encrypted_case(
        key=handshake_key,
        nonce=pair_result_nonce,
        aad_fields={
            **pairing_aad_base,
            "type": "pair_result",
            "created_at": pair_result_created_at,
            "nonce": b64url_encode(pair_result_nonce),
        },
        payload={
            "payload_version": 1,
            "kind": "pair_approved",
            "pair_id": b64url_encode(pair_id),
            "sender_token": b64url_encode(sender_token),
            "pc_label": "Test Windows PC",
            "key_epoch": key_epoch,
        },
    )

    message_key = hkdf_sha256(
        root_key,
        message_id,
        b"wqrs/message-key/v1",
    )
    url_message = encrypted_case(
        key=message_key,
        nonce=message_nonce,
        aad_fields={
            "protocol": PROTOCOL,
            "type": "url_message",
            "pair_id": b64url_encode(pair_id),
            "key_epoch": key_epoch,
            "message_id": b64url_encode(message_id),
            "created_at": message_created_at,
            "expires_at": message_expires_at,
            "nonce": b64url_encode(message_nonce),
        },
        payload={
            "payload_version": 1,
            "kind": "url",
            "url": "https://example.com/path?q=qr",
        },
    )

    ack_key = hkdf_sha256(
        root_key,
        message_id,
        b"wqrs/ack-key/v1",
    )
    delivered_ack = encrypted_case(
        key=ack_key,
        nonce=ack_nonce,
        aad_fields={
            "protocol": PROTOCOL,
            "type": "delivered_ack",
            "pair_id": b64url_encode(pair_id),
            "key_epoch": key_epoch,
            "message_id": b64url_encode(message_id),
            "created_at": ack_created_at,
            "expires_at": ack_expires_at,
            "nonce": b64url_encode(ack_nonce),
        },
        payload={
            "payload_version": 1,
            "kind": "delivered",
            "message_id": b64url_encode(message_id),
        },
    )

    return {
        "vector_version": VECTOR_VERSION,
        "protocol": PROTOCOL,
        "warning": (
            "Public deterministic test data. Never reuse these keys, tokens, "
            "IDs, or nonces in production."
        ),
        "inputs": {
            "pc_private_key": b64url_encode(pc_private_bytes),
            "phone_private_key": b64url_encode(phone_private_bytes),
            "pairing_secret": b64url_encode(pairing_secret),
            "pairing_relay_token": b64url_encode(pairing_relay_token),
            "sender_token": b64url_encode(sender_token),
            "device_id": b64url_encode(device_id),
            "pairing_id": b64url_encode(pairing_id),
            "pair_id": b64url_encode(pair_id),
            "message_id": b64url_encode(message_id),
        },
        "derived": {
            "pc_public_key": b64url_encode(pc_public_bytes),
            "phone_public_key": b64url_encode(phone_public_bytes),
            "shared_secret": b64url_encode(shared_secret),
            "pairing_uri": pairing_uri,
            "pairing_transcript": transcript,
            "pairing_transcript_jcs": transcript_jcs.decode("utf-8"),
            "transcript_hash": b64url_encode(transcript_hash),
            "handshake_key": b64url_encode(handshake_key),
            "root_key": b64url_encode(root_key),
            "message_key": b64url_encode(message_key),
            "ack_key": b64url_encode(ack_key),
        },
        "cases": {
            "pair_request": pair_request,
            "pair_result": pair_result,
            "url_message": url_message,
            "delivered_ack": delivered_ack,
        },
    }


def serialized_vector() -> str:
    return json.dumps(build_vector(), ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed vector differs instead of rewriting it",
    )
    args = parser.parse_args()
    expected = serialized_vector()

    if args.check:
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text("utf-8") != expected:
            print(f"Vector is missing or stale: {OUTPUT_PATH}")
            return 1
        print(f"WQRS/1 vector is current: {OUTPUT_PATH}")
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(expected, encoding="utf-8", newline="\n")
    print(f"Wrote WQRS/1 vector: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
