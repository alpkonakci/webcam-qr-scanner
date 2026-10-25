"""Safe QR payload classification and browser integration."""

from __future__ import annotations

import webbrowser
from urllib.parse import urlparse
from web_urls import validate_web_url


def payload_kind(value: str) -> str:
    """Classify explicit HTTP(S) links without executing the payload."""
    parsed = urlparse(value.strip())
    if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
        return "URL"
    return "Text"


def open_web_url(value: str) -> bool:
    """Open only a valid HTTP(S) URL in the default browser."""
    try:
        clean_value, _, _ = validate_web_url(value.strip())
    except (ValueError, UnicodeError):
        return False

    try:
        return bool(webbrowser.open(clean_value, new=2, autoraise=True))
    except (OSError, webbrowser.Error):
        return False
