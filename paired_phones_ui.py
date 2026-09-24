"""Calm paired-phone management window for the desktop controller."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from home_ui import (
    ACCENT,
    PANEL_BACKGROUND,
    PANEL_HOVER,
    PRIMARY_TEXT,
    SECONDARY_TEXT,
    WARNING,
    WINDOW_BACKGROUND,
    _bring_window_to_front,
    _contains,
    _font_line_height,
    _load_font,
    _primary_screen_size,
)
from native_dialogs import confirm_remove_phone_access
from paired_phone_ipc import PairedPhoneView


WINDOW_TITLE = "QR Scanner - Paired Phones"
WINDOW_WIDTH = 620
WINDOW_HEIGHT = 590
LIST_LEFT = 32
LIST_TOP = 110
LIST_RIGHT = 588
ROW_HEIGHT = 72
ROW_GAP = 10
VISIBLE_ROWS = 4
PAIR_ANOTHER_BOUNDS = (32, 488, 248, 536)
BACK_BOUNDS = (264, 488, 388, 536)
REMOVE_BOUNDS = (404, 488, 588, 536)


class PairedPhonesAction(Enum):
    BACK = "back"
    PAIR_ANOTHER = "pair_another"
    REMOVE = "remove"


@dataclass(frozen=True, slots=True)
class PairedPhonesDecision:
    action: PairedPhonesAction
    phone: PairedPhoneView | None = None


@dataclass(slots=True)
class PairedPhonesWindowState:
    selected_index: int | None = None
    scroll_offset: int = 0
    hover_row: int | None = None
    hover_action: PairedPhonesAction | None = None
    decision: PairedPhonesDecision | None = None


def abbreviated_pair_id(pair_id: str) -> str:
    """Return a recognizable identifier without displaying the full value."""

    if len(pair_id) <= 10:
        return f"{pair_id[:4]}\N{HORIZONTAL ELLIPSIS}{pair_id[-2:]}"
    return f"{pair_id[:6]}\N{HORIZONTAL ELLIPSIS}{pair_id[-4:]}"


def row_at_point(
    x: int,
    y: int,
    *,
    phone_count: int,
    scroll_offset: int,
) -> int | None:
    """Map a pointer position to a visible absolute phone index."""

    if not LIST_LEFT <= x <= LIST_RIGHT or y < LIST_TOP:
        return None
    slot = (y - LIST_TOP) // (ROW_HEIGHT + ROW_GAP)
    if not 0 <= slot < VISIBLE_ROWS:
        return None
    row_top = LIST_TOP + slot * (ROW_HEIGHT + ROW_GAP)
    if y > row_top + ROW_HEIGHT:
        return None
    index = scroll_offset + slot
    return index if index < phone_count else None


def action_at_point(
    x: int,
    y: int,
    *,
    has_selection: bool,
) -> PairedPhonesAction | None:
    if _contains(PAIR_ANOTHER_BOUNDS, x, y):
        return PairedPhonesAction.PAIR_ANOTHER
    if _contains(BACK_BOUNDS, x, y):
        return PairedPhonesAction.BACK
    if has_selection and _contains(REMOVE_BOUNDS, x, y):
        return PairedPhonesAction.REMOVE
    return None


def build_paired_phones_canvas(
    phones: Sequence[PairedPhoneView],
    *,
    selected_index: int | None = None,
    scroll_offset: int = 0,
    hover_row: int | None = None,
    hover_action: PairedPhonesAction | None = None,
) -> np.ndarray:
    """Render labels and abbreviated IDs only; credentials never enter UI."""

    canvas = Image.new("RGB", (WINDOW_WIDTH, WINDOW_HEIGHT), WINDOW_BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    title_font = _load_font(27, semibold=True)
    subtitle_font = _load_font(15)
    label_font = _load_font(17, semibold=True)
    id_font = _load_font(13)
    small_font = _load_font(12)
    button_font = _load_font(14, semibold=True)

    draw.text((32, 24), "SAVED PAIRINGS", font=title_font, fill=PRIMARY_TEXT)
    draw.text(
        (32, 66),
        "Saved approvals, not currently connected phones.",
        font=subtitle_font,
        fill=SECONDARY_TEXT,
    )
    draw.text(
        (32, 87),
        "The same phone can have multiple browser or test pairings.",
        font=small_font,
        fill=SECONDARY_TEXT,
    )

    visible = phones[scroll_offset : scroll_offset + VISIBLE_ROWS]
    for slot, phone in enumerate(visible):
        index = scroll_offset + slot
        top = LIST_TOP + slot * (ROW_HEIGHT + ROW_GAP)
        bounds = (LIST_LEFT, top, LIST_RIGHT, top + ROW_HEIGHT)
        selected = index == selected_index
        hovered = index == hover_row
        draw.rounded_rectangle(
            bounds,
            radius=14,
            fill=PANEL_HOVER if hovered or selected else PANEL_BACKGROUND,
            outline=ACCENT if selected else None,
            width=2 if selected else 1,
        )
        draw.rounded_rectangle(
            (LIST_LEFT + 16, top + 14, LIST_LEFT + 22, top + 58),
            radius=3,
            fill=ACCENT,
        )
        draw.text(
            (LIST_LEFT + 40, top + 11),
            _ellipsize(draw, phone.phone_label, label_font, 350),
            font=label_font,
            fill=PRIMARY_TEXT,
        )
        draw.text(
            (LIST_LEFT + 40, top + 33),
            f"Pair ID  {abbreviated_pair_id(phone.pair_id)}",
            font=id_font,
            fill=SECONDARY_TEXT,
        )
        service = urlsplit(phone.relay_origin).netloc
        draw.text(
            (LIST_LEFT + 40, top + 52),
            _ellipsize(draw, f"Service: {service}", small_font, 490),
            font=small_font,
            fill=SECONDARY_TEXT,
        )

    if len(phones) > VISIBLE_ROWS:
        first = scroll_offset + 1
        last = min(len(phones), scroll_offset + VISIBLE_ROWS)
        draw.text(
            (32, 448),
            f"Showing {first}-{last} of {len(phones)}  \u00b7  Scroll to see more",
            font=small_font,
            fill=SECONDARY_TEXT,
        )
    else:
        draw.text(
            (32, 448),
            "Select a phone to remove its access.",
            font=small_font,
            fill=SECONDARY_TEXT,
        )

    _draw_button(
        draw,
        PAIR_ANOTHER_BOUNDS,
        "Pair another phone",
        button_font,
        hovered=hover_action is PairedPhonesAction.PAIR_ANOTHER,
        accent=ACCENT,
    )
    _draw_button(
        draw,
        BACK_BOUNDS,
        "Back",
        button_font,
        hovered=hover_action is PairedPhonesAction.BACK,
        accent=ACCENT,
    )
    _draw_button(
        draw,
        REMOVE_BOUNDS,
        "Remove access",
        button_font,
        hovered=hover_action is PairedPhonesAction.REMOVE,
        accent=WARNING,
        enabled=selected_index is not None,
    )
    draw.text(
        (32, 558),
        "ESC  Back",
        font=small_font,
        fill=SECONDARY_TEXT,
    )

    rgb = np.asarray(canvas, dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def show_paired_phones_window(
    phones: Sequence[PairedPhoneView],
    *,
    confirm_remove: Callable[[str, str], bool] = confirm_remove_phone_access,
) -> PairedPhonesDecision:
    """Show one management window and return a credential-free decision."""

    items = tuple(phones)
    if not items:
        return PairedPhonesDecision(PairedPhonesAction.BACK)
    state = PairedPhonesWindowState()

    def handle_mouse(
        event: int,
        x: int,
        y: int,
        flags: int,
        _: object,
    ) -> None:
        if event == cv2.EVENT_MOUSEWHEEL:
            direction = -1 if flags > 0 else 1
            new_offset = _clamp_scroll(
                state.scroll_offset + direction,
                len(items),
            )
            state.scroll_offset = new_offset
            selected = state.selected_index
            if (
                selected is not None
                and not new_offset <= selected < new_offset + VISIBLE_ROWS
            ):
                state.selected_index = None
        state.hover_row = row_at_point(
            x,
            y,
            phone_count=len(items),
            scroll_offset=state.scroll_offset,
        )
        state.hover_action = action_at_point(
            x,
            y,
            has_selection=state.selected_index is not None,
        )
        if event != cv2.EVENT_LBUTTONUP:
            return
        if state.hover_row is not None:
            state.selected_index = state.hover_row
            return
        if state.hover_action is PairedPhonesAction.REMOVE:
            assert state.selected_index is not None
            selected = items[state.selected_index]
            if confirm_remove(
                selected.phone_label,
                abbreviated_pair_id(selected.pair_id),
            ):
                state.decision = PairedPhonesDecision(
                    PairedPhonesAction.REMOVE,
                    selected,
                )
        elif state.hover_action is not None:
            state.decision = PairedPhonesDecision(state.hover_action)

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW_TITLE, handle_mouse)
    screen_width, screen_height = _primary_screen_size()
    cv2.moveWindow(
        WINDOW_TITLE,
        max(0, (screen_width - WINDOW_WIDTH) // 2),
        max(0, (screen_height - WINDOW_HEIGHT) // 3),
    )
    try:
        first_frame = True
        while True:
            cv2.imshow(
                WINDOW_TITLE,
                build_paired_phones_canvas(
                    items,
                    selected_index=state.selected_index,
                    scroll_offset=state.scroll_offset,
                    hover_row=state.hover_row,
                    hover_action=state.hover_action,
                ),
            )
            if first_frame:
                _bring_window_to_front(WINDOW_TITLE)
                first_frame = False
            key = cv2.waitKey(16) & 0xFF
            if key == 27:
                return PairedPhonesDecision(PairedPhonesAction.BACK)
            if key in {38, 40, ord("k"), ord("j")}:
                step = -1 if key in {38, ord("k")} else 1
                state.selected_index = _next_selection(
                    state.selected_index,
                    step,
                    len(items),
                )
                state.scroll_offset = _scroll_for_selection(
                    state.scroll_offset,
                    state.selected_index,
                    len(items),
                )
            if cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1:
                return PairedPhonesDecision(PairedPhonesAction.BACK)
            if state.decision is not None:
                return state.decision
    finally:
        try:
            cv2.destroyWindow(WINDOW_TITLE)
        except cv2.error:
            pass


def _clamp_scroll(offset: int, phone_count: int) -> int:
    return max(0, min(offset, max(0, phone_count - VISIBLE_ROWS)))


def _next_selection(current: int | None, step: int, phone_count: int) -> int:
    if current is None:
        return 0 if step >= 0 else phone_count - 1
    return max(0, min(phone_count - 1, current + step))


def _scroll_for_selection(offset: int, selected: int, phone_count: int) -> int:
    if selected < offset:
        return selected
    if selected >= offset + VISIBLE_ROWS:
        return _clamp_scroll(selected - VISIBLE_ROWS + 1, phone_count)
    return offset


def _draw_button(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    text: str,
    font: ImageFont.ImageFont,
    *,
    hovered: bool,
    accent: str,
    enabled: bool = True,
) -> None:
    fill = PANEL_HOVER if hovered and enabled else PANEL_BACKGROUND
    draw.rounded_rectangle(
        bounds,
        radius=11,
        fill=fill,
        outline=accent if hovered and enabled else None,
        width=2 if hovered and enabled else 1,
    )
    text_width = draw.textlength(text, font=font)
    left, top, right, bottom = bounds
    draw.text(
        (
            left + (right - left - text_width) / 2,
            top + (bottom - top - _font_line_height(font)) / 2 - 2,
        ),
        text,
        font=font,
        fill=PRIMARY_TEXT if enabled else SECONDARY_TEXT,
    )


def _ellipsize(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: float,
) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    candidate = text
    while (
        candidate
        and draw.textlength(
            f"{candidate}\N{HORIZONTAL ELLIPSIS}",
            font=font,
        )
        > max_width
    ):
        candidate = candidate[:-1]
    return f"{candidate}\N{HORIZONTAL ELLIPSIS}"
