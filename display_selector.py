"""Minimal monitor picker shown before a multi-display screen scan."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageDraw

from home_ui import (
    ACCENT,
    PANEL_BACKGROUND,
    PANEL_HOVER,
    PRIMARY_TEXT,
    SECONDARY_TEXT,
    WINDOW_BACKGROUND,
    _bring_window_to_front,
    _load_font,
    _primary_screen_size,
)
from screen_capture import ConnectedDisplay


WINDOW_TITLE = "QR Scanner - Choose Screen"
WINDOW_WIDTH = 520
LIST_TOP = 88
ROW_HEIGHT = 62
ROW_GAP = 8
VISIBLE_ROWS = 6
FOOTER_HEIGHT = 42


@dataclass(slots=True)
class DisplaySelectorState:
    scroll_offset: int = 0
    hover_index: int | None = None
    selected: ConnectedDisplay | None = None


def window_height(display_count: int) -> int:
    visible_count = max(1, min(display_count, VISIBLE_ROWS))
    return LIST_TOP + visible_count * (ROW_HEIGHT + ROW_GAP) + FOOTER_HEIGHT


def display_at_point(
    x: int,
    y: int,
    *,
    display_count: int,
    scroll_offset: int,
) -> int | None:
    if not 24 <= x <= WINDOW_WIDTH - 24 or y < LIST_TOP:
        return None
    slot = (y - LIST_TOP) // (ROW_HEIGHT + ROW_GAP)
    if not 0 <= slot < VISIBLE_ROWS:
        return None
    row_top = LIST_TOP + slot * (ROW_HEIGHT + ROW_GAP)
    if y > row_top + ROW_HEIGHT:
        return None
    index = scroll_offset + slot
    return index if index < display_count else None


def build_display_selector_canvas(
    displays: Sequence[ConnectedDisplay],
    *,
    scroll_offset: int = 0,
    hover_index: int | None = None,
) -> np.ndarray:
    height = window_height(len(displays))
    canvas = Image.new("RGB", (WINDOW_WIDTH, height), WINDOW_BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    title_font = _load_font(24, semibold=True)
    subtitle_font = _load_font(14)
    label_font = _load_font(16, semibold=True)
    detail_font = _load_font(12)

    draw.text((24, 18), "CHOOSE A SCREEN", font=title_font, fill=PRIMARY_TEXT)
    draw.text(
        (24, 56),
        "Select the screen that contains the QR code.",
        font=subtitle_font,
        fill=SECONDARY_TEXT,
    )

    visible = displays[scroll_offset : scroll_offset + VISIBLE_ROWS]
    for slot, display in enumerate(visible):
        index = scroll_offset + slot
        top = LIST_TOP + slot * (ROW_HEIGHT + ROW_GAP)
        hovered = index == hover_index
        draw.rounded_rectangle(
            (24, top, WINDOW_WIDTH - 24, top + ROW_HEIGHT),
            radius=13,
            fill=PANEL_HOVER if hovered else PANEL_BACKGROUND,
            outline=ACCENT if hovered else None,
            width=2 if hovered else 1,
        )
        draw.text(
            (44, top + 10),
            f"Screen {display.number}",
            font=label_font,
            fill=PRIMARY_TEXT,
        )
        primary_note = "  ·  Primary" if display.primary else ""
        draw.text(
            (44, top + 36),
            f"{display.bounds.width} × {display.bounds.height}{primary_note}",
            font=detail_font,
            fill=SECONDARY_TEXT,
        )

    footer_y = height - 28
    footer = "Click a screen  ·  ESC Cancel"
    if len(displays) > VISIBLE_ROWS:
        footer = "Scroll for more  ·  Click to select  ·  ESC Cancel"
    draw.text((24, footer_y), footer, font=detail_font, fill=SECONDARY_TEXT)

    return cv2.cvtColor(np.asarray(canvas, dtype=np.uint8), cv2.COLOR_RGB2BGR)


def select_display(
    displays: Sequence[ConnectedDisplay],
) -> ConnectedDisplay | None:
    """Return the monitor clicked by the user, or None when cancelled."""

    items = tuple(displays)
    if not items:
        return None
    if len(items) == 1:
        return items[0]

    state = DisplaySelectorState()

    def handle_mouse(
        event: int,
        x: int,
        y: int,
        flags: int,
        _: object,
    ) -> None:
        if event == cv2.EVENT_MOUSEWHEEL:
            direction = -1 if flags > 0 else 1
            state.scroll_offset = max(
                0,
                min(
                    state.scroll_offset + direction,
                    max(0, len(items) - VISIBLE_ROWS),
                ),
            )
        state.hover_index = display_at_point(
            x,
            y,
            display_count=len(items),
            scroll_offset=state.scroll_offset,
        )
        if event == cv2.EVENT_LBUTTONUP and state.hover_index is not None:
            state.selected = items[state.hover_index]

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW_TITLE, handle_mouse)
    screen_width, screen_height = _primary_screen_size()
    height = window_height(len(items))
    cv2.moveWindow(
        WINDOW_TITLE,
        max(0, (screen_width - WINDOW_WIDTH) // 2),
        max(0, (screen_height - height) // 3),
    )
    try:
        first_frame = True
        while True:
            cv2.imshow(
                WINDOW_TITLE,
                build_display_selector_canvas(
                    items,
                    scroll_offset=state.scroll_offset,
                    hover_index=state.hover_index,
                ),
            )
            if first_frame:
                _bring_window_to_front(WINDOW_TITLE)
                first_frame = False
            key = cv2.waitKey(16) & 0xFF
            if key == 27:
                return None
            if cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1:
                return None
            if state.selected is not None:
                return state.selected
    finally:
        try:
            cv2.destroyWindow(WINDOW_TITLE)
            cv2.waitKey(1)
        except cv2.error:
            pass
