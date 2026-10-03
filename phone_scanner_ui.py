"""Public, reusable homepage QR for returning to the phone scanner."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageDraw

from bridge.protocol import normalize_relay_origin
from home_ui import (
    WINDOW_BACKGROUND, PRIMARY_TEXT, SECONDARY_TEXT, ACCENT,
    _load_font, _bring_window_to_front, _primary_screen_size,
)
from pairing_ui import generate_pairing_qr_image
from window_icon import set_window_icon

WINDOW_TITLE = "QR Scanner - Open Phone Scanner"
WINDOW_WIDTH = 574
WINDOW_HEIGHT = 600
BACK_BOUNDS = (28, 544, 546, 584)


def build_phone_scanner_canvas(origin: str) -> np.ndarray:
    """Show only the public origin, never a credential or private pairing QR."""
    origin = normalize_relay_origin(origin)
    canvas = Image.new("RGB", (WINDOW_WIDTH, WINDOW_HEIGHT), WINDOW_BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    draw.text((28, 22), "OPEN PHONE SCANNER", font=_load_font(25, semibold=True),
              fill=PRIMARY_TEXT)
    draw.text((28, 61), "Scan to reopen. No new pairing needed.",
              font=_load_font(15), fill=SECONDARY_TEXT)
    canvas.paste(generate_pairing_qr_image(origin + "/", size=350), (112, 98))
    draw.text((28, 466), "Use the same phone browser you paired with.",
              font=_load_font(15), fill=PRIMARY_TEXT)
    draw.text((28, 495), "Then tap Scan QR to send a link to this PC.",
              font=_load_font(15), fill=SECONDARY_TEXT)
    draw.rounded_rectangle(BACK_BOUNDS, radius=10, fill="#111C2E")
    draw.text((264, 553), "Back", font=_load_font(15, semibold=True), fill=ACCENT)
    return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)


def show_phone_scanner_window(origin: str) -> None:
    canvas = build_phone_scanner_canvas(origin)
    closed = False

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        nonlocal closed
        left, top, right, bottom = BACK_BOUNDS
        if event == cv2.EVENT_LBUTTONUP and left <= x <= right and top <= y <= bottom:
            closed = True

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_AUTOSIZE)
    set_window_icon(WINDOW_TITLE)
    cv2.setMouseCallback(WINDOW_TITLE, on_mouse)
    width, height = _primary_screen_size()
    cv2.moveWindow(WINDOW_TITLE, max(0, (width - WINDOW_WIDTH) // 2),
                   max(0, (height - WINDOW_HEIGHT) // 3))
    try:
        cv2.imshow(WINDOW_TITLE, canvas)
        _bring_window_to_front(WINDOW_TITLE)
        while not closed:
            if cv2.waitKey(16) & 0xFF == 27:
                break
            if cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        try:
            cv2.destroyWindow(WINDOW_TITLE)
        except cv2.error:
            pass
