"""OpenCV-based presentation layer for the camera preview."""

from __future__ import annotations

import os
import time

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2
import numpy as np

from links import payload_kind
from qr_reader import QRResult
from scan_geometry import scan_region


WINDOW_TITLE = "Webcam QR Scanner"
DISPLAY_SIZE = (1280, 720)

COLOR_ACCENT = (191, 212, 45)  # Turquoise #2DD4BF
COLOR_SUCCESS = (94, 197, 34)  # Green #22C55E
COLOR_WARNING = (11, 158, 245)  # Amber #F59E0B
COLOR_PANEL = (32, 18, 11)  # Graphite #0B1220
COLOR_TEXT = (252, 250, 248)  # Off-white #F8FAFC
COLOR_MUTED = (225, 213, 203)  # Light blue-gray #CBD5E1


def readable_preview(value: str, limit: int = 70) -> str:
    """Create single-line text supported by OpenCV's built-in font."""
    single_line = " ".join(value.splitlines())
    ascii_text = single_line.encode("ascii", errors="replace").decode("ascii")
    return ascii_text if len(ascii_text) <= limit else f"{ascii_text[: limit - 3]}..."


def is_exit_key(key: int) -> bool:
    """The application intentionally reserves only Escape for exit."""
    return key == 27


def fps_color(fps: float) -> tuple[int, int, int]:
    """Reserve green for successful QR detection, not normal performance."""
    return COLOR_ACCENT if fps >= 24.0 else COLOR_WARNING


def ui_scale(frame: np.ndarray) -> float:
    """Keep the interface readable at different camera resolutions."""
    height, width = frame.shape[:2]
    return max(0.75, min(1.25, min(width / 1600, height / 900)))


def draw_translucent_panel(
    frame: np.ndarray,
    top_left: tuple[int, int],
    bottom_right: tuple[int, int],
    *,
    alpha: float = 0.68,
    radius: int = 18,
) -> None:
    """Draw a rounded, translucent dark panel in-place."""
    x1, y1 = top_left
    x2, y2 = bottom_right
    radius = max(1, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    overlay = frame.copy()

    cv2.rectangle(overlay, (x1 + radius, y1), (x2 - radius, y2), COLOR_PANEL, -1)
    cv2.rectangle(overlay, (x1, y1 + radius), (x2, y2 - radius), COLOR_PANEL, -1)
    for center in (
        (x1 + radius, y1 + radius),
        (x2 - radius, y1 + radius),
        (x1 + radius, y2 - radius),
        (x2 - radius, y2 - radius),
    ):
        cv2.circle(overlay, center, radius, COLOR_PANEL, -1, cv2.LINE_AA)

    cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)


def draw_scan_guide(frame: np.ndarray, scale: float, animation_time: float) -> None:
    """Draw corner markers and a subtle animated scanning line."""
    height, width = frame.shape[:2]
    left, top, right, bottom = scan_region((width, height))
    size = right - left
    corner = int(size * 0.16)
    thickness = max(2, int(3 * scale))

    segments = (
        ((left, top + corner), (left, top), (left + corner, top)),
        ((right - corner, top), (right, top), (right, top + corner)),
        ((left, bottom - corner), (left, bottom), (left + corner, bottom)),
        ((right - corner, bottom), (right, bottom), (right, bottom - corner)),
    )

    for first, corner_point, last in segments:
        cv2.line(frame, first, corner_point, (15, 18, 22), thickness + 5, cv2.LINE_AA)
        cv2.line(frame, corner_point, last, (15, 18, 22), thickness + 5, cv2.LINE_AA)
        cv2.line(frame, first, corner_point, COLOR_ACCENT, thickness, cv2.LINE_AA)
        cv2.line(frame, corner_point, last, COLOR_ACCENT, thickness, cv2.LINE_AA)

    phase = (animation_time % 2.8) / 2.8
    progress = phase * 2.0 if phase <= 0.5 else (1.0 - phase) * 2.0
    line_y = int(top + corner * 0.65 + progress * (size - corner * 1.3))
    line_left = left + int(corner * 0.45)
    line_right = right - int(corner * 0.45)
    overlay = frame.copy()
    cv2.line(
        overlay,
        (line_left, line_y),
        (line_right, line_y),
        COLOR_ACCENT,
        max(1, int(2 * scale)),
        cv2.LINE_AA,
    )
    cv2.addWeighted(overlay, 0.48, frame, 0.52, 0, frame)


def draw_result(frame: np.ndarray, result: QRResult) -> None:
    """Draw a successful QR outline and a compact payload card."""
    scale = ui_scale(frame)
    corners = result.corners.reshape((-1, 1, 2))
    cv2.polylines(
        frame,
        [corners],
        True,
        COLOR_SUCCESS,
        max(3, int(5 * scale)),
        cv2.LINE_AA,
    )

    x, y = result.corners[0]
    label = f"{payload_kind(result.data)}: {readable_preview(result.data)}"
    font_scale = 0.58 * scale
    thickness = max(1, int(2 * scale))
    (text_width, text_height), baseline = cv2.getTextSize(
        label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
    )
    box_x = max(16, min(int(x), frame.shape[1] - text_width - 42))
    box_y = max(16, int(y) - text_height - baseline - 34)
    draw_translucent_panel(
        frame,
        (box_x, box_y),
        (box_x + text_width + 28, box_y + text_height + baseline + 22),
        alpha=0.76,
        radius=max(8, int(12 * scale)),
    )
    cv2.putText(
        frame,
        label,
        (box_x + 14, box_y + text_height + 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        COLOR_SUCCESS,
        thickness,
        cv2.LINE_AA,
    )


def show_instructions(
    frame: np.ndarray,
    detected: bool = False,
    fps: float | None = None,
    animation_time: float | None = None,
) -> None:
    """Render the camera UI without covering the full top edge."""
    height, width = frame.shape[:2]
    scale = ui_scale(frame)
    margin = int(28 * scale)
    panel_height = int(108 * scale)
    panel_width = min(width - 2 * margin, int(710 * scale))
    panel_left = margin
    panel_top = margin

    draw_translucent_panel(
        frame,
        (panel_left, panel_top),
        (panel_left + panel_width, panel_top + panel_height),
        alpha=0.68,
        radius=int(20 * scale),
    )

    icon_size = int(54 * scale)
    icon_left = panel_left + int(22 * scale)
    icon_top = panel_top + (panel_height - icon_size) // 2
    cv2.rectangle(
        frame,
        (icon_left, icon_top),
        (icon_left + icon_size, icon_top + icon_size),
        COLOR_ACCENT,
        max(2, int(3 * scale)),
        cv2.LINE_AA,
    )
    marker = int(13 * scale)
    inset = int(9 * scale)
    for marker_x, marker_y in (
        (icon_left + inset, icon_top + inset),
        (icon_left + icon_size - inset - marker, icon_top + inset),
        (icon_left + inset, icon_top + icon_size - inset - marker),
    ):
        cv2.rectangle(
            frame,
            (marker_x, marker_y),
            (marker_x + marker, marker_y + marker),
            COLOR_ACCENT,
            -1,
        )

    text_left = icon_left + icon_size + int(22 * scale)
    cv2.putText(
        frame,
        "QR SCANNER",
        (text_left, panel_top + int(45 * scale)),
        cv2.FONT_HERSHEY_DUPLEX,
        0.90 * scale,
        COLOR_TEXT,
        max(2, int(2 * scale)),
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        "Place the QR code inside the frame",
        (text_left, panel_top + int(78 * scale)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.56 * scale,
        COLOR_MUTED,
        max(1, int(2 * scale)),
        cv2.LINE_AA,
    )

    if fps is not None:
        _draw_fps_badge(frame, fps, scale, margin)

    draw_scan_guide(
        frame,
        scale,
        time.monotonic() if animation_time is None else animation_time,
    )
    _draw_status_panel(frame, detected, scale, margin)


def _draw_fps_badge(
    frame: np.ndarray,
    fps: float,
    scale: float,
    margin: int,
) -> None:
    fps_text = f"{fps:4.1f} FPS" if fps > 0 else "FPS --"
    font_scale = 0.58 * scale
    thickness = max(1, int(2 * scale))
    (fps_width, fps_height), _ = cv2.getTextSize(
        fps_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
    )
    badge_width = fps_width + int(44 * scale)
    badge_height = int(54 * scale)
    badge_right = frame.shape[1] - margin
    badge_top = margin
    draw_translucent_panel(
        frame,
        (badge_right - badge_width, badge_top),
        (badge_right, badge_top + badge_height),
        alpha=0.68,
        radius=int(17 * scale),
    )
    cv2.putText(
        frame,
        fps_text,
        (
            badge_right - badge_width + int(22 * scale),
            badge_top + (badge_height + fps_height) // 2,
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        fps_color(fps),
        thickness,
        cv2.LINE_AA,
    )


def _draw_status_panel(
    frame: np.ndarray,
    detected: bool,
    scale: float,
    margin: int,
) -> None:
    status_text = "QR code detected" if detected else "Waiting for QR code"
    control_text = "ESC   Exit"
    font_scale = 0.54 * scale
    thickness = max(1, int(2 * scale))
    (status_width, status_height), _ = cv2.getTextSize(
        status_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
    )
    (control_width, _), _ = cv2.getTextSize(
        control_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
    )
    bottom_width = status_width + control_width + int(100 * scale)
    bottom_height = int(58 * scale)
    bottom_left = max(margin, (frame.shape[1] - bottom_width) // 2)
    bottom_top = frame.shape[0] - margin - bottom_height
    draw_translucent_panel(
        frame,
        (bottom_left, bottom_top),
        (bottom_left + bottom_width, bottom_top + bottom_height),
        alpha=0.68,
        radius=int(18 * scale),
    )

    dot_x = bottom_left + int(24 * scale)
    dot_y = bottom_top + bottom_height // 2
    status_color = COLOR_SUCCESS if detected else COLOR_ACCENT
    cv2.circle(
        frame,
        (dot_x, dot_y),
        max(4, int(6 * scale)),
        status_color,
        -1,
        cv2.LINE_AA,
    )
    baseline_y = dot_y + status_height // 2
    cv2.putText(
        frame,
        status_text,
        (dot_x + int(18 * scale), baseline_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        COLOR_TEXT,
        thickness,
        cv2.LINE_AA,
    )
    separator_x = dot_x + int(18 * scale) + status_width + int(24 * scale)
    cv2.line(
        frame,
        (separator_x, bottom_top + int(15 * scale)),
        (separator_x, bottom_top + bottom_height - int(15 * scale)),
        (90, 96, 106),
        max(1, int(scale)),
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        control_text,
        (separator_x + int(24 * scale), baseline_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        COLOR_MUTED,
        thickness,
        cv2.LINE_AA,
    )
