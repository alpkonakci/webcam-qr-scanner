"""Small runtime performance helpers."""

from __future__ import annotations

import time


class FPSCounter:
    """Calculate a smoothed frame rate for the camera preview."""

    def __init__(self, smoothing: float = 0.9) -> None:
        self.smoothing = smoothing
        self._last_time: float | None = None
        self.value = 0.0

    def tick(self, now: float | None = None) -> float:
        current = time.perf_counter() if now is None else now
        if self._last_time is not None:
            elapsed = current - self._last_time
            if elapsed > 0:
                instant = 1.0 / elapsed
                self.value = (
                    instant
                    if self.value == 0.0
                    else self.smoothing * self.value
                    + (1.0 - self.smoothing) * instant
                )
        self._last_time = current
        return self.value
