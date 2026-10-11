"""Offline QR creation with explicit payload limits and a quiet border."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import cv2
from PIL import Image


MAX_CREATE_BYTES = 600


@dataclass(frozen=True, slots=True)
class CreatedQR:
    value: str
    kind: str
    image: Image.Image


def validate_creation_value(value: str, kind: str) -> str:
    if kind not in {"link", "text"}:
        raise ValueError("Choose Link or Text.")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter a link or some text first.")
    value = value.strip() if kind == "link" else value
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as error:
        raise ValueError("The content contains unsupported characters.") from error
    if size > MAX_CREATE_BYTES:
        raise ValueError("Use a shorter link or text (maximum 600 UTF-8 bytes).")
    if any((ord(char) < 32 and char not in "\r\n\t") or ord(char) == 127 for char in value):
        raise ValueError("Remove unsupported control characters.")
    if kind == "link":
        try:
            parsed = urlsplit(value)
            _ = parsed.port  # Validate malformed or out-of-range ports.
            if (parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or any(char.isspace() for char in value)):
                raise ValueError
        except ValueError as error:
            raise ValueError("Enter a complete HTTP/HTTPS link without embedded credentials.") from error
    return value


def create_qr(value: str, kind: str = "link") -> CreatedQR:
    value = validate_creation_value(value, kind)
    parameters = cv2.QRCodeEncoder_Params()
    parameters.correction_level = cv2.QRCodeEncoder_CORRECT_LEVEL_M
    try:
        matrix = cv2.QRCodeEncoder_create(parameters).encode(value)
    except cv2.error as error:
        raise ValueError("This content could not be encoded. Try shorter text.") from error
    if matrix is None or matrix.ndim != 2:
        raise ValueError("This content could not be encoded.")
    # OpenCV's encoder includes a two-module border. Add two more so the
    # exported image has the standard four-module white quiet zone.
    matrix = cv2.copyMakeBorder(matrix, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=255)
    image = Image.fromarray(matrix).convert("RGB")
    scale = max(4, 512 // image.width)
    image = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    return CreatedQR(value, kind, image)
