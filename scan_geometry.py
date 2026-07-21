"""Shared geometry for the visible guide and the real QR scan area."""

from __future__ import annotations

import numpy as np

from qr_reader import QRResult


def scan_region(size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Return the exact square used by both the UI guide and QR analysis."""
    width, height = size
    region_size = min(int(height * 0.48), int(width * 0.34))
    center_x = width // 2
    center_y = int(height * 0.54)
    left = center_x - region_size // 2
    top = center_y - region_size // 2
    return left, top, left + region_size, top + region_size


def crop_scan_region(frame: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
    """Copy the scan region so the camera can immediately reuse its frame."""
    height, width = frame.shape[:2]
    left, top, right, bottom = scan_region((width, height))
    return frame[top:bottom, left:right].copy(), (left, top)


def offset_results(
    results: list[QRResult],
    offset: tuple[int, int],
) -> list[QRResult]:
    """Map scan-region coordinates back to the original camera frame."""
    if not results:
        return []
    translation = np.array(offset, dtype=np.int32)
    return [
        QRResult(result.data, result.corners + translation)
        for result in results
    ]


def scale_result(
    result: QRResult,
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> QRResult:
    """Map detector coordinates to the displayed camera frame."""
    source_width, source_height = source_size
    target_width, target_height = target_size
    factors = np.array(
        [target_width / source_width, target_height / source_height],
        dtype=np.float32,
    )
    corners = np.rint(result.corners.astype(np.float32) * factors).astype(np.int32)
    return QRResult(result.data, corners)
