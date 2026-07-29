"""Interactive, one-shot selection when a screen contains multiple QR codes."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from urllib.parse import urlparse

import cv2
import numpy as np

from links import payload_kind
from qr_reader import QRResult
from scan_geometry import scale_result
from ui import COLOR_ACCENT, COLOR_MUTED, COLOR_PANEL, COLOR_TEXT


WINDOW_TITLE = "Scan Screen - Choose QR"
HEADER_HEIGHT = 94
DEFAULT_SCREEN_SIZE = (1280, 720)
WINDOW_WIDTH_RATIO = 0.90
WINDOW_HEIGHT_RATIO = 0.82
HIT_PADDING = 14


@dataclass(slots=True)
class SelectorState:
    """Mutable mouse state owned by one selector window."""

    hover_index: int | None = None
    selected_index: int | None = None


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


def display_results(
    results: list[QRResult],
    source_size: tuple[int, int],
    preview_size: tuple[int, int],
) -> list[QRResult]:
    """Map detector coordinates into the selector canvas."""

    vertical_offset = np.array([0, HEADER_HEIGHT], dtype=np.int32)
    return [
        QRResult(
            result.data,
            scale_result(result, source_size, preview_size).corners
            + vertical_offset,
        )
        for result in results
    ]


def nearest_result_index(
    results: list[QRResult],
    point: tuple[int, int],
) -> int | None:
    """Find the nearest QR for hover feedback only."""

    if not results:
        return None
    cursor = np.asarray(point, dtype=np.float32)
    distances = [
        float(np.linalg.norm(result.corners.mean(axis=0) - cursor))
        for result in results
    ]
    return int(np.argmin(distances))


def result_index_at_point(
    results: list[QRResult],
    point: tuple[int, int],
    *,
    padding: int = HIT_PADDING,
) -> int | None:
    """Return a QR only when the user clicks its padded visible bounds."""

    x, y = point
    candidates: list[int] = []
    for index, result in enumerate(results):
        left, top, width, height = cv2.boundingRect(result.corners)
        if (
            left - padding <= x <= left + width + padding
            and top - padding <= y <= top + height + padding
        ):
            candidates.append(index)
    if not candidates:
        return None
    candidate_results = [results[index] for index in candidates]
    nearest = nearest_result_index(candidate_results, point)
    return candidates[nearest] if nearest is not None else None


def result_label(result: QRResult, number: int) -> str:
    """Build a short ASCII label that OpenCV can render reliably."""

    if payload_kind(result.data) != "URL":
        return f"{number}  Text QR"
    host = urlparse(result.data).hostname or "unknown host"
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        host = "unknown host"
    return f"{number}  {host[:48]}"


def build_selector_canvas(
    frame: np.ndarray,
    results: list[QRResult],
    *,
    hover_index: int | None = None,
    window_limit: tuple[int, int] | None = None,
) -> tuple[np.ndarray, list[QRResult]]:
    """Render a frozen desktop preview and return its mapped QR results."""

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
    mapped_results = display_results(results, source_size, preview_size)

    cv2.putText(
        canvas,
        "MULTIPLE QR CODES FOUND",
        (24, 34),
        cv2.FONT_HERSHEY_DUPLEX,
        0.72,
        COLOR_TEXT,
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        "Click the QR code you want to scan",
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

    for index, result in enumerate(mapped_results):
        hovered = index == hover_index
        outline_color = COLOR_TEXT if hovered else COLOR_ACCENT
        thickness = 4 if hovered else 2
        overlay = canvas.copy()
        cv2.fillPoly(overlay, [result.corners], COLOR_ACCENT, cv2.LINE_AA)
        alpha = 0.16 if hovered else 0.08
        cv2.addWeighted(overlay, alpha, canvas, 1.0 - alpha, 0, canvas)
        cv2.polylines(
            canvas,
            [result.corners.reshape((-1, 1, 2))],
            True,
            outline_color,
            thickness,
            cv2.LINE_AA,
        )
        _draw_result_label(
            canvas,
            result,
            result_label(result, index + 1),
            hovered=hovered,
        )

    return canvas, mapped_results


def _draw_result_label(
    canvas: np.ndarray,
    result: QRResult,
    label: str,
    *,
    hovered: bool,
) -> None:
    font_scale = 0.48
    thickness = 1
    (text_width, text_height), baseline = cv2.getTextSize(
        label,
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        thickness,
    )
    left, top, _, height = cv2.boundingRect(result.corners)
    label_width = text_width + 20
    label_height = text_height + baseline + 14
    label_left = max(4, min(left, canvas.shape[1] - label_width - 4))
    label_top = top - label_height - 6
    if label_top < HEADER_HEIGHT:
        label_top = min(
            canvas.shape[0] - label_height - 4,
            top + height + 6,
        )
    cv2.rectangle(
        canvas,
        (label_left, label_top),
        (label_left + label_width, label_top + label_height),
        COLOR_PANEL,
        -1,
    )
    cv2.rectangle(
        canvas,
        (label_left, label_top),
        (label_left + label_width, label_top + label_height),
        COLOR_TEXT if hovered else COLOR_ACCENT,
        1,
    )
    cv2.putText(
        canvas,
        label,
        (label_left + 10, label_top + text_height + 6),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        COLOR_TEXT,
        thickness,
        cv2.LINE_AA,
    )


def select_screen_result(
    frame: np.ndarray,
    results: list[QRResult],
) -> QRResult | None:
    """Let the user explicitly click one QR; Escape and window close cancel."""

    if not results:
        return None

    state = SelectorState()
    initial_canvas, mapped_results = build_selector_canvas(frame, results)

    def handle_mouse(
        event: int,
        x: int,
        y: int,
        _: int,
        __: object,
    ) -> None:
        state.hover_index = nearest_result_index(mapped_results, (x, y))
        if event == cv2.EVENT_LBUTTONUP:
            state.selected_index = result_index_at_point(
                mapped_results,
                (x, y),
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
        while state.selected_index is None:
            canvas, _ = build_selector_canvas(
                frame,
                results,
                hover_index=state.hover_index,
            )
            cv2.imshow(WINDOW_TITLE, canvas)
            if cv2.waitKey(16) & 0xFF == 27:
                return None
            if cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1:
                return None
        return results[state.selected_index]
    finally:
        try:
            cv2.destroyWindow(WINDOW_TITLE)
        except cv2.error:
            pass
