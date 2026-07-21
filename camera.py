"""Webcam access for the QR scanner application."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2
import numpy as np


class CameraError(RuntimeError):
    """Raised when the selected camera cannot be used."""


@dataclass(frozen=True)
class CameraConfig:
    index: int = 0
    width: int = 1920
    height: int = 1080
    fps: int = 30
    fallback_width: int = 1280
    fallback_height: int = 720
    minimum_fps: float = 24.0
    warmup_frames: int = 4
    sample_frames: int = 12


class CameraStream:
    """Small, testable wrapper around OpenCV's VideoCapture."""

    def __init__(self, config: CameraConfig) -> None:
        self.config = config
        self._capture: cv2.VideoCapture | None = None
        self.resolution: tuple[int, int] = (0, 0)
        self.measured_fps = 0.0

    def _configure_and_measure(
        self,
        capture: cv2.VideoCapture,
        width: int,
        height: int,
    ) -> tuple[tuple[int, int], float] | None:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        capture.set(cv2.CAP_PROP_FPS, self.config.fps)

        frame: np.ndarray | None = None
        for _ in range(self.config.warmup_frames):
            success, frame = capture.read()
            if not success or frame is None:
                return None

        start = time.perf_counter()
        completed = 0
        for _ in range(self.config.sample_frames):
            success, frame = capture.read()
            if success and frame is not None:
                completed += 1
        elapsed = time.perf_counter() - start

        if completed == 0 or frame is None or elapsed <= 0:
            return None
        actual_height, actual_width = frame.shape[:2]
        return (actual_width, actual_height), completed / elapsed

    @staticmethod
    def _matches(actual: tuple[int, int], expected: tuple[int, int]) -> bool:
        return abs(actual[0] - expected[0]) <= 2 and abs(actual[1] - expected[1]) <= 2

    def open(self) -> None:
        backends: list[int | None] = (
            [cv2.CAP_MSMF, cv2.CAP_DSHOW, None] if os.name == "nt" else [None]
        )

        for backend in backends:
            capture = (
                cv2.VideoCapture(self.config.index, backend)
                if backend is not None
                else cv2.VideoCapture(self.config.index)
            )

            if capture.isOpened():
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                primary_size = (self.config.width, self.config.height)
                primary = self._configure_and_measure(capture, *primary_size)
                if primary is None:
                    capture.release()
                    continue

                selected = primary
                primary_supported = self._matches(primary[0], primary_size)
                primary_fast_enough = primary[1] >= self.config.minimum_fps

                if not primary_supported or not primary_fast_enough:
                    fallback_size = (
                        self.config.fallback_width,
                        self.config.fallback_height,
                    )
                    fallback = self._configure_and_measure(capture, *fallback_size)
                    fallback_supported = (
                        fallback is not None
                        and self._matches(fallback[0], fallback_size)
                    )
                    fallback_is_better = (
                        fallback is not None
                        and (
                            not primary_supported
                            or fallback[1] >= self.config.minimum_fps
                            or fallback[1] > primary[1] + 1.0
                        )
                    )

                    if fallback_supported and fallback_is_better:
                        selected = fallback
                    elif primary_supported:
                        restored = self._configure_and_measure(capture, *primary_size)
                        if restored is not None:
                            selected = restored

                self.resolution, self.measured_fps = selected
                self._capture = capture
                return

            capture.release()

        raise CameraError(
            f"Camera {self.config.index} could not be opened. Check camera permission "
            "and whether another application is using the camera."
        )

    def read(self) -> np.ndarray:
        if self._capture is None:
            raise CameraError("The camera has not been opened yet.")

        success, frame = self._capture.read()
        if not success or frame is None:
            raise CameraError("Could not read a frame from the camera.")
        return frame

    def release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def __enter__(self) -> "CameraStream":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()
