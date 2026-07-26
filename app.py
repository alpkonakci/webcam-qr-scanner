"""Application entry point for the live webcam QR scanner."""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime
from enum import Enum, auto
from typing import Sequence
from urllib.parse import urlparse

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2
import numpy as np

from camera import CameraConfig, CameraError, CameraStream
from links import open_web_url, payload_kind
from performance import FPSCounter
from qr_reader import QRReader, QRResult
from screen_capture import ScreenCaptureError, capture_virtual_screen
from scan_geometry import scale_result, scan_region
from scan_worker import QRScanWorker, ScanGate
from ui import DISPLAY_SIZE, WINDOW_TITLE, draw_result, is_exit_key, show_instructions


def show_dialog(title: str, message: str, style: int = 0) -> int:
    """Show a native Windows message box and return the selected button."""
    if os.name == "nt":
        return int(ctypes.windll.user32.MessageBoxW(0, message, title, style))
    return 0


def show_error_dialog(title: str, message: str) -> None:
    """Show an error when the Windows application has no terminal."""
    show_dialog(title, message, 0x10)


class ScreenScanStatus(Enum):
    """Observable outcomes of a one-shot screen scan."""

    NO_CODE = auto()
    MULTIPLE_CODES = auto()
    TEXT_FOUND = auto()
    CANCELLED = auto()
    OPENED = auto()
    OPEN_FAILED = auto()


def _dialog_preview(value: str, limit: int = 900) -> str:
    """Keep decoded text readable and bounded inside a native dialog."""
    clean_value = "".join(
        character if character.isprintable() or character in "\r\n\t" else "�"
        for character in value.strip()
    )
    if len(clean_value) <= limit:
        return clean_value
    return f"{clean_value[: limit - 3]}..."


def _unique_results(results: list[QRResult]) -> list[QRResult]:
    """Collapse duplicate detections while preserving distinct payloads."""
    unique: list[QRResult] = []
    seen: set[str] = set()
    for result in results:
        clean_value = result.data.strip()
        if clean_value and clean_value not in seen:
            seen.add(clean_value)
            unique.append(QRResult(clean_value, result.corners))
    return unique


def confirm_screen_url(value: str) -> bool:
    """Ask before opening a URL discovered in a screen capture."""
    host = urlparse(value).hostname or "(unknown host)"
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    message = (
        "A QR code on the screen contains this web address.\n\n"
        f"Website:\n{host}\n\n"
        f"Full address:\n{_dialog_preview(value)}\n\n"
        "Open it in the default browser?"
    )
    # Yes/No, warning icon, and No as the default button.
    return show_dialog("Scan Screen - Confirm link", message, 0x04 | 0x30 | 0x100) == 6


def run_screen_scan(
    *,
    capture: Callable[[], np.ndarray] | None = None,
    reader: QRReader | None = None,
    confirm: Callable[[str], bool] | None = None,
    opener: Callable[[str], bool] | None = None,
    notify: Callable[[str, str, int], int] | None = None,
) -> ScreenScanStatus:
    """Capture all displays once, decode one QR, and safely handle its payload."""
    capture = capture or capture_virtual_screen
    reader = reader or QRReader()
    confirm = confirm or confirm_screen_url
    opener = opener or open_web_url
    notify = notify or show_dialog

    print("Scanning all connected screens once...")
    results = _unique_results(reader.scan(capture(), thorough=True))

    if not results:
        notify(
            "Scan Screen",
            "No QR code was found. Make the QR code clearly visible and try again.",
            0x40,
        )
        return ScreenScanStatus.NO_CODE

    if len(results) > 1:
        notify(
            "Scan Screen",
            (
                "Multiple QR codes were found. Nothing was opened.\n\n"
                "Keep only one QR code visible and try again."
            ),
            0x30,
        )
        return ScreenScanStatus.MULTIPLE_CODES

    value = results[0].data
    if payload_kind(value) != "URL":
        notify(
            "Scan Screen - Text QR",
            (
                "The QR code does not contain a valid HTTP/HTTPS web address."
                f"\n\nDecoded text:\n{_dialog_preview(value)}"
            ),
            0x40,
        )
        return ScreenScanStatus.TEXT_FOUND

    if not confirm(value):
        return ScreenScanStatus.CANCELLED

    if opener(value):
        print("Link opened in the default browser.")
        return ScreenScanStatus.OPENED

    notify(
        "Scan Screen - Browser error",
        "The link could not be opened in the default browser.",
        0x10,
    )
    return ScreenScanStatus.OPEN_FAILED


def _report_scan(result: QRResult, auto_open: bool) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    kind = payload_kind(result.data)
    print(f"[{timestamp}] {kind} scanned: {result.data}")
    if kind != "URL" or not auto_open:
        return

    if open_web_url(result.data):
        print("  Link opened in the default browser.")
    else:
        print("  The link could not be opened in the browser.")


def _draw_preview(
    frame: np.ndarray,
    results: list[QRResult],
    fps: float | None,
    now: float,
) -> np.ndarray:
    preview = cv2.resize(frame, DISPLAY_SIZE, interpolation=cv2.INTER_AREA)
    source_size = (frame.shape[1], frame.shape[0])
    for result in results:
        draw_result(preview, scale_result(result, source_size, DISPLAY_SIZE))
    show_instructions(
        preview,
        detected=bool(results),
        fps=fps,
        animation_time=now,
    )
    return preview


def run(
    camera_index: int,
    auto_open: bool = True,
    exit_after_scan: bool = True,
    show_fps: bool = False,
) -> None:
    """Run the camera loop until Escape, window close, or a successful scan."""
    scan_gate = ScanGate()
    fps_counter = FPSCounter()

    print("Opening camera...")
    print("Press ESC in the camera window to exit.")

    with (
        CameraStream(CameraConfig(index=camera_index)) as camera,
        QRScanWorker() as scanner,
    ):
        print(
            f"Camera ready: {camera.resolution[0]}x{camera.resolution[1]} "
            f"at approximately {camera.measured_fps:.1f} FPS."
        )
        cv2.namedWindow(WINDOW_TITLE, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_TITLE, *DISPLAY_SIZE)

        result_version = 0
        visible_results: list[QRResult] = []
        visible_until = 0.0

        while True:
            frame = camera.read()
            now = time.monotonic()
            display_fps = fps_counter.tick(now) if show_fps else None
            scanner.submit(frame)
            result_version, fresh_results = scanner.poll(result_version)

            if fresh_results:
                visible_results = fresh_results
                visible_until = now + 0.6
            elif fresh_results is not None and now >= visible_until:
                visible_results = []

            close_after_scan = False
            for result in fresh_results or []:
                if not scan_gate.should_trigger(result.data, now):
                    continue
                _report_scan(result, auto_open)
                if exit_after_scan:
                    print("QR code scanned; closing the application.")
                    close_after_scan = True
                    break

            if close_after_scan:
                break

            scan_gate.prune(now)
            cv2.imshow(
                WINDOW_TITLE,
                _draw_preview(frame, visible_results, display_fps, now),
            )

            key = cv2.waitKey(1) & 0xFF
            if is_exit_key(key):
                break
            if cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1:
                break

    cv2.destroyAllWindows()


def _self_test_frame(value: str) -> np.ndarray:
    """Build a deterministic camera-like frame for packaged smoke tests."""
    encoder = cv2.QRCodeEncoder_create()
    qr_image = encoder.encode(value)
    qr_image = cv2.copyMakeBorder(
        qr_image,
        4,
        4,
        4,
        4,
        cv2.BORDER_CONSTANT,
        value=255,
    )
    qr_image = cv2.resize(qr_image, (240, 240), interpolation=cv2.INTER_NEAREST)
    frame = np.full((720, 1280, 3), 255, dtype=np.uint8)
    left, top, right, bottom = scan_region((1280, 720))
    x = (left + right - qr_image.shape[1]) // 2
    y = (top + bottom - qr_image.shape[0]) // 2
    frame[y : y + 240, x : x + 240] = cv2.cvtColor(
        qr_image,
        cv2.COLOR_GRAY2BGR,
    )
    return frame


def run_self_test(timeout: float = 3.0) -> bool:
    """Verify bundled OpenCV imports and background QR decoding without a camera."""
    expected = "https://example.com/qr-scanner-self-test"
    version = 0
    results: list[QRResult] | None = None
    with QRScanWorker(thorough_every=1) as scanner:
        scanner.submit(_self_test_frame(expected))
        deadline = time.monotonic() + timeout
        while results is None and time.monotonic() < deadline:
            version, results = scanner.poll(version)
            time.sleep(0.01)
    return bool(results and any(result.data == expected for result in results))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan QR codes with your computer camera.")
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Camera index (default: 0)",
    )
    parser.add_argument(
        "--no-open",
        action="store_false",
        dest="auto_open",
        help="Do not open QR links automatically in the browser",
    )
    parser.add_argument(
        "--keep-open",
        action="store_false",
        dest="exit_after_scan",
        help="Continue scanning instead of closing after the first scan",
    )
    parser.add_argument(
        "--show-fps",
        action="store_true",
        help="Show the developer FPS overlay",
    )
    parser.add_argument(
        "--screen",
        action="store_true",
        help="Scan all connected screens once instead of opening the camera",
    )
    parser.add_argument("--desktop", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return 0 if run_self_test() else 1

    desktop_mode = args.desktop or bool(getattr(sys, "frozen", False))
    try:
        if args.screen:
            status = run_screen_scan()
            return 1 if status is ScreenScanStatus.OPEN_FAILED else 0

        run(
            args.camera,
            auto_open=args.auto_open,
            exit_after_scan=args.exit_after_scan,
            show_fps=args.show_fps,
        )
    except CameraError as error:
        print(f"Camera error: {error}")
        if desktop_mode:
            show_error_dialog("QR Scanner - Camera error", str(error))
        return 1
    except ScreenCaptureError as error:
        print(f"Screen capture error: {error}")
        if desktop_mode:
            show_error_dialog("Scan Screen - Capture error", str(error))
        return 1
    except cv2.error as error:
        print(f"OpenCV error: {error}")
        if desktop_mode:
            show_error_dialog("QR Scanner - Application error", str(error))
        return 1
    except KeyboardInterrupt:
        print("\nApplication closed.")
    finally:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
