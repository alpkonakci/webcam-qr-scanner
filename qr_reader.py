"""QR code detection and decoding."""

from __future__ import annotations

import os
from dataclasses import dataclass

# Must be set before importing cv2. This suppresses OpenCV's noisy ECI warning
# while preserving genuine errors.
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2
import numpy as np


@dataclass(frozen=True)
class QRResult:
    data: str
    corners: np.ndarray


class QRReader:
    """Decode one or more QR codes from an OpenCV image."""

    def __init__(self) -> None:
        self._detector = cv2.QRCodeDetector()

    @staticmethod
    def _corners(points: np.ndarray) -> np.ndarray:
        return np.asarray(points, dtype=np.int32).reshape(-1, 2)

    def _scan_once(self, image: np.ndarray) -> list[QRResult]:
        results: list[QRResult] = []

        try:
            detected, decoded_values, points, _ = self._detector.detectAndDecodeMulti(image)
            if detected and points is not None:
                for value, qr_points in zip(decoded_values, points):
                    if value:
                        results.append(QRResult(value, self._corners(qr_points)))
        except cv2.error:
            # Some camera frames or OpenCV builds may reject multi-detection.
            # Single-code detection below remains a reliable fallback.
            pass

        if results:
            return results

        value, points, _ = self._detector.detectAndDecode(image)
        if value and points is not None:
            results.append(QRResult(value, self._corners(points)))
        return results

    @staticmethod
    def _restore_scale(results: list[QRResult], scale: float) -> list[QRResult]:
        return [
            QRResult(
                result.data,
                np.rint(result.corners.astype(np.float32) / scale).astype(np.int32),
            )
            for result in results
        ]

    def scan(self, frame: np.ndarray, thorough: bool = True) -> list[QRResult]:
        if frame is None or frame.size == 0:
            return []

        height, width = frame.shape[:2]

        # Start with a smaller frame. It is substantially faster and resampling
        # also reduces moiré patterns caused by filming a phone display.
        if width > 960:
            scale = 960.0 / width
            reduced = cv2.resize(
                frame,
                (960, max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
            results = self._scan_once(reduced)
            if results:
                return self._restore_scale(results, scale)
            if not thorough:
                return []
        else:
            results = self._scan_once(frame)
            if results or not thorough:
                return results

        # Periodic thorough scans preserve small/distant QR detection without
        # making every displayed camera frame pay the Full HD processing cost.
        if width > 960:
            results = self._scan_once(frame)
            if results:
                return results

        # A small blur softens display pixels; equalization improves contrast
        # when the phone screen is bright or illumination is uneven.
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        softened = cv2.GaussianBlur(gray, (3, 3), 0)
        enhanced = cv2.equalizeHist(softened)
        return self._scan_once(enhanced)
