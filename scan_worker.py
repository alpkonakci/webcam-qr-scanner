"""Non-blocking QR analysis that always prioritizes the newest frame."""

from __future__ import annotations

import os
import threading

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2
import numpy as np

from qr_reader import QRReader, QRResult
from scan_geometry import crop_scan_region, offset_results


SCAN_REARM_SECONDS = 2.0


class ScanGate:
    """Trigger once, then re-arm after the same QR has been absent."""

    def __init__(self, rearm_seconds: float = SCAN_REARM_SECONDS) -> None:
        self.rearm_seconds = rearm_seconds
        self._last_seen: dict[str, float] = {}

    def should_trigger(self, value: str, now: float) -> bool:
        previous = self._last_seen.get(value)
        self._last_seen[value] = now
        return previous is None or now - previous >= self.rearm_seconds

    def prune(self, now: float, max_age: float = 300.0) -> None:
        self._last_seen = {
            value: seen_at
            for value, seen_at in self._last_seen.items()
            if now - seen_at < max_age
        }


class QRScanWorker:
    """Analyze only the newest scan-region frame without blocking the UI."""

    def __init__(self, thorough_every: int = 6) -> None:
        self.thorough_every = max(1, thorough_every)
        self._reader = QRReader()
        self._lock = threading.Lock()
        self._frame_ready = threading.Event()
        self._stop_requested = threading.Event()
        self._pending_frame: tuple[np.ndarray, tuple[int, int]] | None = None
        self._latest_results: list[QRResult] = []
        self._result_version = 0
        self._scan_count = 0
        self._thread = threading.Thread(
            target=self._work,
            name="qr-scan-worker",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def submit(self, frame: np.ndarray) -> None:
        # Replacing the pending frame prevents latency from accumulating.
        cropped, offset = crop_scan_region(frame)
        with self._lock:
            self._pending_frame = (cropped, offset)
            self._frame_ready.set()

    def poll(self, previous_version: int) -> tuple[int, list[QRResult] | None]:
        with self._lock:
            if self._result_version == previous_version:
                return previous_version, None
            return self._result_version, list(self._latest_results)

    def _work(self) -> None:
        while not self._stop_requested.is_set():
            self._frame_ready.wait(timeout=0.1)
            if self._stop_requested.is_set():
                break

            with self._lock:
                pending = self._pending_frame
                self._pending_frame = None
                self._frame_ready.clear()

            if pending is None:
                continue

            frame, offset = pending
            self._scan_count += 1
            thorough = self._scan_count % self.thorough_every == 0
            try:
                results = self._reader.scan(frame, thorough=thorough)
            except cv2.error:
                results = []

            with self._lock:
                self._latest_results = offset_results(results, offset)
                self._result_version += 1

    def close(self) -> None:
        self._stop_requested.set()
        self._frame_ready.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def __enter__(self) -> "QRScanWorker":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
