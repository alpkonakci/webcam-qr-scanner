"""One destination identity for desktop confirmations and browser navigation."""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

import idna

MAX_WEB_URL_BYTES = 4096


def validate_web_url(value: object) -> tuple[str, str, bool]:
    """Return a canonical authority, display host and HTTPS flag or fail closed.

    Preserve path/query/fragment bytes. UTS46 non-transitional processing keeps
    deviation characters such as sharp-s distinct, unlike Python's IDNA2003.
    Legacy numeric IPv4 spellings and percent-encoded hosts are not accepted.
    """
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("URL must be nonempty without surrounding whitespace")
    if len(value.encode("utf-8")) > MAX_WEB_URL_BYTES:
        raise ValueError("URL exceeds the 4096-byte limit")
    if any(ord(character) < 32 or ord(character) == 127 for character in value) or "\\" in value:
        raise ValueError("URL contains a control character or backslash")
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname or "://" not in value:
        raise ValueError("only absolute HTTP(S) URLs are accepted")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are forbidden")
    port = parsed.port  # Reject invalid/out-of-range ports before navigation.
    host = parsed.hostname
    if "%" in host:
        raise ValueError("encoded or scoped URL hostnames are unsupported")
    if ":" in host:
        address = ipaddress.IPv6Address(host)
        host = address.compressed
        if address.ipv4_mapped is not None:
            # WHATWG serializes mapped IPv4 in hex, not dotted decimal.
            mapped = int(address.ipv4_mapped)
            host = f"::ffff:{mapped >> 16:x}:{mapped & 0xffff:x}"
        authority = f"[{host}]"
    else:
        host = idna.encode(host, uts46=True, std3_rules=True, transitional=False).decode("ascii").lower()
        # Browsers interpret a numeric final label using legacy IPv4 parsing.
        # Accept only strict dotted-decimal IPv4 to avoid a different display.
        last_label = host.rstrip(".").rsplit(".", 1)[-1]
        if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]*)", last_label):
            host = str(ipaddress.IPv4Address(host))
        authority = host
    if port is not None:
        authority += f":{port}"
    suffix_start = value.index("://") + 3 + len(parsed.netloc)
    canonical = f"{scheme}://{authority}{value[suffix_start:]}"
    if len(canonical.encode("utf-8")) > MAX_WEB_URL_BYTES:
        raise ValueError("canonical URL exceeds the 4096-byte limit")
    return canonical, host, scheme == "https"
