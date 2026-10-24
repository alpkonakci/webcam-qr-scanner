"""Optional, origin-scoped access to a protected Vercel preview relay."""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlsplit

from bridge.protocol import normalize_relay_origin


BYPASS_ORIGIN_ENV = "WQRS_VERCEL_BYPASS_ORIGIN"
BYPASS_SECRET_ENV = "WQRS_VERCEL_BYPASS_SECRET"
BYPASS_HEADER = "x-vercel-protection-bypass"


def relay_protection_headers(
    relay_origin: str,
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a bypass header only for the explicitly selected Vercel origin.

    The secret is never placed in a URL, and unrelated relay/Supabase origins
    cannot receive it. A partially configured test fails before any request.
    """

    source = os.environ if environment is None else environment
    configured_origin = source.get(BYPASS_ORIGIN_ENV, "")
    secret = source.get(BYPASS_SECRET_ENV, "")
    if not configured_origin and not secret:
        return {}
    if not configured_origin or not secret:
        raise ValueError("Vercel preview bypass configuration is incomplete")

    target = normalize_relay_origin(configured_origin)
    hostname = urlsplit(target).hostname or ""
    if not target.startswith("https://") or not hostname.endswith(".vercel.app"):
        raise ValueError("Vercel preview bypass origin must be HTTPS on vercel.app")
    if not secret.isascii() or any(character.isspace() for character in secret):
        raise ValueError("Vercel preview bypass secret has an invalid format")

    if normalize_relay_origin(relay_origin) != target:
        return {}
    return {BYPASS_HEADER: secret}
