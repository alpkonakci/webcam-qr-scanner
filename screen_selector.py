"""Interactive in-memory region selection for one-shot screen scanning."""

from __future__ import annotations

import ctypes
import math
import os
from dataclasses import dataclass

import cv2
import numpy as np

from ui import COLOR_ACCENT, COLOR_MUTED, COLOR_PANEL, COLOR_TEXT


WINDOW_TITLE = "Scan Screen - Select Area"
HEADER_HEIGHT = 94
DEFAULT_SCREEN_SIZE = (1280, 720)
WINDOW_WIDTH_RATIO = 0.90
WINDOW_HEIGHT_RATIO = 0.82
MINIMUM_SELECTION_SIZE = 12

PreviewRegion = tuple[int, int, int, int]


@dataclass(slots=True)
class RegionSelectorState:
    """Mouse state owned by one selector window."""

    start: tuple[int, int] | None = None
    current: tuple[int, int] | None = None
    selected: PreviewRegion | None = None
    dragging: bool = False


def primary_screen_size() -> tuple[int, int]:
    """Return the primary display size, with a test-friendly fallback."""

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


def selector_window_limit(
    screen_size: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Leave room for window borders, the taskbar, and other OS chrome."""

    width, height = screen_size or primary_screen_size()
    return (
        max(640, int(width * WINDOW_WIDTH_RATIO)),
        max(360, int(height * WINDOW_HEIGHT_RATIO)),
    )


def selector_preview_size(
    source_size: tuple[int, int],
    window_limit: tuple[int, int],
) -> tuple[int, int]:
    """Fit the complete virtual desktop without changing its aspect ratio."""

    source_width, source_height = source_size
    maximum_width, maximum_height = window_limit
    available_height = max(1, maximum_height - HEADER_HEIGHT)
    scale = min(
        maximum_width / source_width,
        available_height / source_height,
        1.0,
    )
    return (
        max(1, int(round(source_width * scale))),
        max(1, int(round(source_height * scale))),
    )


def normalize_preview_region(
    start: tuple[int, int],
    end: tuple[int, int],
    preview_size: tuple[int, int],
    *,
    minimum_size: int = MINIMUM_SELECTION_SIZE,
) -> PreviewRegion | None:
    """Normalize, clamp, and validate a drag rectangle in preview pixels."""

    width, height = preview_size
    first_x = max(0, min(start[0], width))
    second_x = max(0, min(end[0], width))
    first_y = max(0, min(start[1], height))
    second_y = max(0, min(end[1], height))
    left, right = sorted((first_x, second_x))
    top, bottom = sorted((first_y, second_y))
    if right - left < minimum_size or bottom - top < minimum_size:
        return None
    return left, top, right, bottom


def map_preview_region_to_source(
    region: PreviewRegion,
    source_size: tuple[int, int],
    preview_size: tuple[int, int],
) -> PreviewRegion:
    """Map a validated preview rectangle back to source image pixels."""

    source_width, source_height = source_size
    preview_width, preview_height = preview_size
    left, top, right, bottom = region
    source_region = (
        max(0, math.floor(left * source_width / preview_width)),
        max(0, math.floor(top * source_height / preview_height)),
        min(source_width, math.ceil(right * source_width / preview_width)),
        min(source_height, math.ceil(bottom * source_height / preview_height)),
    )
    if source_region[2] <= source_region[0] or source_region[3] <= source_region[1]:
        raise ValueError("selected screen region is empty")
    return source_region


def crop_screen_region(
    frame: np.ndarray,
    region: PreviewRegion,
    preview_size: tuple[int, int],
) -> np.ndarray:
    """Return an independent in-memory crop for the selected preview area."""

    left, top, right, bottom = map_preview_region_to_source(
        region,
        (frame.shape[1], frame.shape[0]),
        preview_size,
    )
    return frame[top:bottom, left:right].copy()


def build_region_selector_canvas(
    frame: np.ndarray,
    *,
    selection: PreviewRegion | None = None,
    window_limit: tuple[int, int] | None = None,
) -> tuple[np.ndarray, tuple[int, int]]:
    """Render a frozen desktop preview with an optional drag rectangle."""

    source_size = (frame.shape[1], frame.shape[0])
    preview_size = selector_preview_size(
        source_size,
        window_limit or selector_window_limit(),
    )
    interpolation = (
        cv2.INTER_AREA
        if preview_size[0] < source_size[0]
        else cv2.INTER_LINEAR
    )
    preview = cv2.resize(frame, preview_size, interpolation=interpolation)
    canvas = np.full(
        (preview_size[1] + HEADER_HEIGHT, preview_size[0], 3),
        COLOR_PANEL,
        dtype=np.uint8,
    )
    canvas[HEADER_HEIGHT:, :] = preview

    cv2.putText(
        canvas,
        "SELECT QR AREA",
        (24, 34),
        cv2.FONT_HERSHEY_DUPLEX,
        0.72,
        COLOR_TEXT,
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        "Drag around one QR code and release to scan",
        (24, 65),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.57,
        COLOR_MUTED,
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        "ESC  Cancel",
        (max(24, preview_size[0] - 132), 65),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        COLOR_MUTED,
        1,
        cv2.LINE_AA,
    )

    if selection is not None:
        left, top, right, bottom = selection
        image = canvas[HEADER_HEIGHT:, :]
        dimmed = np.zeros_like(image)
        cv2.addWeighted(image, 0.42, dimmed, 0.58, 0, dimmed)
        dimmed[top:bottom, left:right] = preview[top:bottom, left:right]
        canvas[HEADER_HEIGHT:, :] = dimmed
        cv2.rectangle(
            canvas,
            (left, top + HEADER_HEIGHT),
            (right, bottom + HEADER_HEIGHT),
            COLOR_ACCENT,
            3,
            cv2.LINE_AA,
        )

    return canvas, preview_size


def select_screen_region(frame: np.ndarray) -> np.ndarray | None:
    """Let the user drag one screen area; Escape and close cancel safely."""

    state = RegionSelectorState()
    initial_canvas, preview_size = build_region_selector_canvas(frame)
    preview_width, preview_height = preview_size

    def preview_point(x: int, y: int) -> tuple[int, int]:
        return (
            max(0, min(x, preview_width)),
            max(0, min(y - HEADER_HEIGHT, preview_height)),
        )

    def handle_mouse(
        event: int,
        x: int,
        y: int,
        _: int,
        __: object,
    ) -> None:
        if event == cv2.EVENT_LBUTTONDOWN and y >= HEADER_HEIGHT:
            state.start = preview_point(x, y)
            state.current = state.start
            state.selected = None
            state.dragging = True
            return
        if event == cv2.EVENT_MOUSEMOVE and state.dragging:
            state.current = preview_point(x, y)
            return
        if event == cv2.EVENT_LBUTTONUP and state.dragging:
            state.current = preview_point(x, y)
            state.dragging = False
            if state.start is not None:
                state.selected = normalize_preview_region(
                    state.start,
                    state.current,
                    preview_size,
                )

    cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW_TITLE, handle_mouse)
    screen_width, screen_height = primary_screen_size()
    cv2.moveWindow(
        WINDOW_TITLE,
        max(0, (screen_width - initial_canvas.shape[1]) // 2),
        max(0, (screen_height - initial_canvas.shape[0]) // 3),
    )
    try:
        cv2.setWindowProperty(WINDOW_TITLE, cv2.WND_PROP_TOPMOST, 1)
    except cv2.error:
        pass

    try:
        while state.selected is None:
            drag_region = None
            if state.start is not None and state.current is not None:
                drag_region = normalize_preview_region(
                    state.start,
                    state.current,
                    preview_size,
                    minimum_size=1,
                )
            canvas, _ = build_region_selector_canvas(
                frame,
                selection=drag_region,
            )
            cv2.imshow(WINDOW_TITLE, canvas)
            if cv2.waitKey(16) & 0xFF == 27:
                return None
            if cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1:
                return None
        return crop_screen_region(frame, state.selected, preview_size)
    finally:
        try:
            cv2.destroyWindow(WINDOW_TITLE)
        except cv2.error:
            pass
