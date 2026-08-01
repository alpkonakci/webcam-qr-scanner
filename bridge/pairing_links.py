"""Safe browser launch links for install-free phone pairing."""

from __future__ import annotations

from urllib.parse import urlencode, urlsplit

from bridge.protocol import (
    b64url_decode,
    b64url_encode,
    normalize_relay_origin,
    parse_pairing_uri,
)


PUBLIC_SERVICE_ORIGIN = "https://webcam-qr-scanner-pwa.alpkon.chatgpt.site"
PAIRING_URI_PREFIX = "wqrs://pair?"
COMPACT_FRAGMENT_PREFIX = "p1."
COMPACT_PAYLOAD_BYTES = 138
P256_PRIME = (1 << 256) - (1 << 224) + (1 << 192) + (1 << 96) - 1
P256_B = int(
    "5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B",
    16,
)


def build_pairing_launch_url(
    pairing_uri: str,
    *,
    pwa_origin: str = PUBLIC_SERVICE_ORIGIN,
) -> str:
    """Wrap a WQRS URI in an HTTPS fragment that never reaches the server."""

    if not pairing_uri.startswith(PAIRING_URI_PREFIX):
        raise ValueError("pairing URI target is invalid")
    origin = normalize_relay_origin(pwa_origin)
    if not origin.startswith("https://"):
        raise ValueError("the public pairing app must use HTTPS")
    pairing = parse_pairing_uri(pairing_uri)
    if pairing.relay_origin == origin:
        compact_payload = b"".join(
            (
                b"\x01",
                b64url_decode(pairing.device_id, expected_length=16),
                b64url_decode(pairing.pairing_id, expected_length=16),
                b64url_decode(pairing.pairing_token, expected_length=32),
                _compress_p256_point(pairing.pc_public_key),
                pairing.pairing_secret,
                pairing.expires_at.to_bytes(8, "big"),
            )
        )
        return (
            f"{origin}/#{COMPACT_FRAGMENT_PREFIX}"
            f"{b64url_encode(compact_payload)}"
        )
    return f"{origin}/#{pairing_uri}"


def extract_pairing_uri(
    value: str,
    *,
    pwa_origin: str = PUBLIC_SERVICE_ORIGIN,
) -> str:
    """Read a direct development URI or an official HTTPS launch fragment."""

    if value.startswith(PAIRING_URI_PREFIX):
        return value

    parsed = urlsplit(value)
    expected_origin = normalize_relay_origin(pwa_origin)
    actual_origin = normalize_relay_origin(
        f"{parsed.scheme}://{parsed.netloc}"
    )
    if (
        actual_origin != expected_origin
        or parsed.path not in {"", "/"}
        or parsed.query
    ):
        raise ValueError("pairing launch URL is invalid")
    if parsed.fragment.startswith(PAIRING_URI_PREFIX):
        return parsed.fragment
    if not parsed.fragment.startswith(COMPACT_FRAGMENT_PREFIX):
        raise ValueError("pairing launch URL is invalid")
    encoded_payload = parsed.fragment.removeprefix(COMPACT_FRAGMENT_PREFIX)
    payload = b64url_decode(
        encoded_payload,
        expected_length=COMPACT_PAYLOAD_BYTES,
    )
    if payload[0] != 1:
        raise ValueError("compact pairing fragment version is unsupported")
    device_id = b64url_encode(payload[1:17])
    pairing_id = b64url_encode(payload[17:33])
    pairing_token = b64url_encode(payload[33:65])
    pc_key = b64url_encode(_decompress_p256_point(payload[65:98]))
    secret = b64url_encode(payload[98:130])
    expires = str(int.from_bytes(payload[130:138], "big"))
    return PAIRING_URI_PREFIX + urlencode(
        {
            "v": "1",
            "relay": expected_origin,
            "device": device_id,
            "pairing": pairing_id,
            "pairing_token": pairing_token,
            "pc_key": pc_key,
            "secret": secret,
            "expires": expires,
        }
    )


def _compress_p256_point(point: bytes) -> bytes:
    if len(point) != 65 or point[0] != 4:
        raise ValueError("P-256 public key is invalid")
    prefix = 2 | (point[-1] & 1)
    return bytes((prefix,)) + point[1:33]


def _decompress_p256_point(point: bytes) -> bytes:
    if len(point) != 33 or point[0] not in {2, 3}:
        raise ValueError("compressed P-256 public key is invalid")
    x = int.from_bytes(point[1:], "big")
    if x >= P256_PRIME:
        raise ValueError("compressed P-256 public key is invalid")
    right_side = (pow(x, 3, P256_PRIME) - 3 * x + P256_B) % P256_PRIME
    y = pow(right_side, (P256_PRIME + 1) // 4, P256_PRIME)
    if pow(y, 2, P256_PRIME) != right_side:
        raise ValueError("compressed P-256 public key is invalid")
    if (y & 1) != (point[0] & 1):
        y = P256_PRIME - y
    return b"\x04" + point[1:] + y.to_bytes(32, "big")
