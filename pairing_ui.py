"""Modern, short-lived pairing QR window for the desktop controller."""

from __future__ import annotations

import ctypes
import math
import os
import threading
import time
from enum import Enum
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


WINDOW_TITLE = "QR Scanner - Pair Phone"
WINDOW_WIDTH = 574
WINDOW_HEIGHT = 720
WINDOW_BACKGROUND = "#0B1220"
PANEL_BACKGROUND = "#111C2E"
PRIMARY_TEXT = "#F8FAFC"
SECONDARY_TEXT = "#A7B2C4"
ACCENT = "#2DD4BF"
WARNING = "#FBBF24"
QR_SIZE = 414
DEFAULT_SCREEN_SIZE = (1280, 720)


class PairingWindowOutcome(Enum):
    REQUEST_RECEIVED = "request_received"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


def pairing_seconds_remaining(
    expires_at: int,
    *,
    now: float | None = None,
) -> int:
    """Return a non-negative, user-facing ceiling for the QR lifetime."""

    current_time = time.time() if now is None else now
    return max(0, math.ceil(expires_at - current_time))


def generate_pairing_qr_image(
    pairing_value: str,
    *,
    size: int = QR_SIZE,
) -> Image.Image:
    """Encode the pairing launch value in memory without files or clipboard."""

    if not pairing_value:
        raise ValueError("pairing value must not be empty")
    if size < 160:
        raise ValueError("pairing QR image is too small")

    encoder = cv2.QRCodeEncoder_create()
    matrix = encoder.encode(pairing_value)
    if matrix is None or matrix.ndim != 2:
        raise RuntimeError("OpenCV could not encode the pairing QR")
    qr = Image.fromarray(matrix).convert("L")
    qr = ImageOps.expand(qr, border=4, fill=255)
    module_scale = size // qr.width
    if module_scale < 1:
        raise ValueError("pairing QR image is too small for its payload")
    scaled_size = qr.width * module_scale
    qr = qr.resize(
        (scaled_size, scaled_size),
        Image.Resampling.NEAREST,
    ).convert("RGB")
    image = Image.new("RGB", (size, size), "white")
    offset = (size - scaled_size) // 2
    image.paste(qr, (offset, offset))
    return image


def build_pairing_canvas(
    qr_image: Image.Image,
    *,
    remaining_seconds: int,
    relay_origin: str,
    development_mode: bool,
) -> np.ndarray:
    """Render the complete sharp-text pairing view as an OpenCV BGR image."""

    canvas = Image.new(
        "RGB",
        (WINDOW_WIDTH, WINDOW_HEIGHT),
        WINDOW_BACKGROUND,
    )
    draw = ImageDraw.Draw(canvas)
    title_font = _load_font(26, semibold=True)
    body_font = _load_font(15)
    body_bold_font = _load_font(15, semibold=True)
    detail_font = _load_font(13)
    countdown_font = _load_font(18, semibold=True)

    draw.text(
        (28, 22),
        "PAIR A PHONE",
        font=title_font,
        fill=PRIMARY_TEXT,
    )
    draw.text(
        (28, 58),
        "Scan this code with your phone camera.",
        font=body_font,
        fill=SECONDARY_TEXT,
    )

    draw.rounded_rectangle(
        (28, 92, WINDOW_WIDTH - 28, 566),
        radius=18,
        fill=PANEL_BACKGROUND,
    )
    qr = qr_image.convert("RGB")
    if qr.size != (QR_SIZE, QR_SIZE):
        qr = qr.resize((QR_SIZE, QR_SIZE), Image.Resampling.NEAREST)
    canvas.paste(qr, ((WINDOW_WIDTH - QR_SIZE) // 2, 108))

    countdown = f"Expires in {max(0, remaining_seconds)} seconds"
    countdown_width = draw.textlength(countdown, font=countdown_font)
    draw.text(
        ((WINDOW_WIDTH - countdown_width) / 2, 532),
        countdown,
        font=countdown_font,
        fill=ACCENT,
    )

    draw.text(
        (28, 580),
        "Keep this window visible while pairing.",
        font=body_bold_font,
        fill=PRIMARY_TEXT,
    )
    _draw_wrapped_text(
        draw,
        (
            "The code expires after two minutes and can be used only once. "
            "You will still confirm the device before access is granted."
        ),
        position=(28, 606),
        maximum_width=WINDOW_WIDTH - 56,
        font=detail_font,
        fill=SECONDARY_TEXT,
        line_spacing=4,
    )

    relay_text = f"Relay: {relay_origin}"
    if development_mode:
        relay_text += (
            "\nLocal development mode — a real phone cannot connect yet."
        )
    _draw_wrapped_text(
        draw,
        relay_text,
        position=(28, 666),
        maximum_width=WINDOW_WIDTH - 56,
        font=detail_font,
        fill=WARNING if development_mode else SECONDARY_TEXT,
        line_spacing=3,
    )

    rgb = np.asarray(canvas, dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def show_pairing_qr_window(
    pairing_value: str,
    *,
    expires_at: int,
    request_received: threading.Event,
    cancel_requested: threading.Event | None,
    relay_origin: str,
    development_mode: bool,
) -> PairingWindowOutcome:
    """Show one QR until a request arrives, the user exits, or it expires."""

    qr_image = generate_pairing_qr_image(pairing_value)
    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_AUTOSIZE)
    screen_width, screen_height = _primary_screen_size()
    cv2.moveWindow(
        WINDOW_TITLE,
        max(0, (screen_width - WINDOW_WIDTH) // 2),
        max(0, (screen_height - WINDOW_HEIGHT) // 3),
    )
    try:
        cv2.setWindowProperty(WINDOW_TITLE, cv2.WND_PROP_TOPMOST, 1)
    except cv2.error:
        pass

    try:
        while True:
            if cancel_requested is not None and cancel_requested.is_set():
                return PairingWindowOutcome.CANCELLED
            if request_received.is_set():
                return PairingWindowOutcome.REQUEST_RECEIVED

            remaining = pairing_seconds_remaining(expires_at)
            if remaining <= 0:
                return PairingWindowOutcome.EXPIRED
            canvas = build_pairing_canvas(
                qr_image,
                remaining_seconds=remaining,
                relay_origin=relay_origin,
                development_mode=development_mode,
            )
            cv2.imshow(WINDOW_TITLE, canvas)
            if cv2.waitKey(100) & 0xFF == 27:
                return PairingWindowOutcome.CANCELLED
            if (
                cv2.getWindowProperty(
                    WINDOW_TITLE,
                    cv2.WND_PROP_VISIBLE,
                )
                < 1
            ):
                return PairingWindowOutcome.CANCELLED
    finally:
        try:
            cv2.destroyWindow(WINDOW_TITLE)
        except cv2.error:
            pass


def _load_font(size: int, *, semibold: bool = False) -> ImageFont.ImageFont:
    windows_directory = Path(os.environ.get("WINDIR", r"C:\Windows"))
    filename = "seguisb.ttf" if semibold else "segoeui.ttf"
    try:
        return ImageFont.truetype(
            str(windows_directory / "Fonts" / filename),
            size=size,
        )
    except OSError:
        return ImageFont.load_default()


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    position: tuple[int, int],
    maximum_width: int,
    font: ImageFont.ImageFont,
    fill: str,
    line_spacing: int,
) -> None:
    """Draw newline-aware, width-bounded text without external layout tools."""

    x, y = position
    line_height = _font_line_height(font) + line_spacing
    for paragraph in text.splitlines() or ("",):
        words = paragraph.split()
        current_line = ""
        for word in words:
            candidate = f"{current_line} {word}".strip()
            if (
                not current_line
                or draw.textlength(candidate, font=font) <= maximum_width
            ):
                current_line = candidate
                continue
            draw.text((x, y), current_line, font=font, fill=fill)
            y += line_height
            current_line = word
        draw.text((x, y), current_line, font=font, fill=fill)
        y += line_height


def _font_line_height(font: ImageFont.ImageFont) -> int:
    _, top, _, bottom = font.getbbox("Ag")
    return max(1, bottom - top)


def _primary_screen_size() -> tuple[int, int]:
    if os.name != "nt":
        return DEFAULT_SCREEN_SIZE
    try:
        user32 = ctypes.windll.user32
        width = int(user32.GetSystemMetrics(0))
        height = int(user32.GetSystemMetrics(1))
        if width > 0 and height > 0:
            return width, height
    except (AttributeError, OSError):
        pass
    return DEFAULT_SCREEN_SIZE
