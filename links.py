"""Safe QR payload classification and browser integration."""

from __future__ import annotations

import webbrowser
from urllib.parse import urlparse


def payload_kind(value: str) -> str:
    """Classify explicit HTTP(S) links without executing the payload."""
    parsed = urlparse(value.strip())
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        return "URL"
    return "Text"


def open_web_url(value: str) -> bool:
    """Open only a valid HTTP(S) URL in the default browser."""
    clean_value = value.strip()
    if payload_kind(clean_value) != "URL":
        return False

    try:
        return bool(webbrowser.open(clean_value, new=2, autoraise=True))
    except (OSError, webbrowser.Error):
        return False
