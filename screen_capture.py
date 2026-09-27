"""One-shot Windows desktop capture for screen QR scanning."""

from __future__ import annotations

import ctypes
import os
import re
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass

import numpy as np


class ScreenCaptureError(RuntimeError):
    """Raised when Windows cannot capture the virtual desktop."""


@dataclass(frozen=True, slots=True)
class ScreenBounds:
    """Position and size of the virtual desktop in Windows coordinates."""

    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class ConnectedDisplay:
    """One physical monitor exposed by Windows."""

    number: int
    device_name: str
    bounds: ScreenBounds
    primary: bool = False


SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
BI_RGB = 0
DIB_RGB_COLORS = 0
MONITORINFOF_PRIMARY = 1


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class RGBQUAD(ctypes.Structure):
    _fields_ = [
        ("rgbBlue", wintypes.BYTE),
        ("rgbGreen", wintypes.BYTE),
        ("rgbRed", wintypes.BYTE),
        ("rgbReserved", wintypes.BYTE),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", RGBQUAD * 1),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


def virtual_screen_bounds(
    get_metric: Callable[[int], int],
) -> ScreenBounds:
    """Read the rectangle containing every connected display."""
    bounds = ScreenBounds(
        left=int(get_metric(SM_XVIRTUALSCREEN)),
        top=int(get_metric(SM_YVIRTUALSCREEN)),
        width=int(get_metric(SM_CXVIRTUALSCREEN)),
        height=int(get_metric(SM_CYVIRTUALSCREEN)),
    )
    if bounds.width <= 0 or bounds.height <= 0:
        raise ScreenCaptureError("Windows reported an invalid desktop size.")
    return bounds


def _display_sort_key(
    item: tuple[str, ScreenBounds, bool],
) -> tuple[int, str]:
    match = re.search(r"(\d+)$", item[0])
    return (int(match.group(1)) if match else 2**31 - 1, item[0].casefold())


def number_connected_displays(
    displays: list[tuple[str, ScreenBounds, bool]],
) -> tuple[ConnectedDisplay, ...]:
    """Apply stable Windows display numbers to enumerated monitor records."""

    ordered = sorted(displays, key=_display_sort_key)
    return tuple(
        ConnectedDisplay(
            number=index,
            device_name=device_name,
            bounds=bounds,
            primary=primary,
        )
        for index, (device_name, bounds, primary) in enumerate(ordered, start=1)
    )


def connected_displays() -> tuple[ConnectedDisplay, ...]:
    """Return every connected physical monitor in Windows display order."""

    if os.name != "nt":
        raise ScreenCaptureError("Screen scanning currently supports Windows only.")

    user32 = ctypes.windll.user32
    _enable_dpi_awareness(user32)
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )
    user32.GetMonitorInfoW.argtypes = [
        wintypes.HMONITOR,
        ctypes.POINTER(MONITORINFOEXW),
    ]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.EnumDisplayMonitors.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(RECT),
        callback_type,
        wintypes.LPARAM,
    ]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    records: list[tuple[str, ScreenBounds, bool]] = []

    def collect_monitor(
        monitor: wintypes.HMONITOR,
        _: wintypes.HDC,
        __: ctypes.POINTER(RECT),
        ___: wintypes.LPARAM,
    ) -> bool:
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return True
        rect = info.rcMonitor
        bounds = ScreenBounds(
            left=int(rect.left),
            top=int(rect.top),
            width=int(rect.right - rect.left),
            height=int(rect.bottom - rect.top),
        )
        if bounds.width > 0 and bounds.height > 0:
            records.append(
                (
                    str(info.szDevice),
                    bounds,
                    bool(info.dwFlags & MONITORINFOF_PRIMARY),
                )
            )
        return True

    callback = callback_type(collect_monitor)
    if not user32.EnumDisplayMonitors(None, None, callback, 0) or not records:
        raise ScreenCaptureError("Windows could not list the connected displays.")
    return number_connected_displays(records)


def _enable_dpi_awareness(user32: ctypes.WinDLL) -> None:
    """Request physical-pixel coordinates before reading screen dimensions."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _configure_gdi(user32: ctypes.WinDLL, gdi32: ctypes.WinDLL) -> None:
    """Declare pointer-sized Windows API signatures for 64-bit safety."""
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int

    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
    ]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.BitBlt.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.LPVOID,
        ctypes.POINTER(BITMAPINFO),
        wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL


def capture_screen_bounds(bounds: ScreenBounds) -> np.ndarray:
    """Capture one Windows screen rectangle as an in-memory BGR image."""

    if os.name != "nt":
        raise ScreenCaptureError("Screen scanning currently supports Windows only.")
    if bounds.width <= 0 or bounds.height <= 0:
        raise ScreenCaptureError("Windows reported an invalid screen size.")

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    _enable_dpi_awareness(user32)
    _configure_gdi(user32, gdi32)

    screen_dc = user32.GetDC(None)
    if not screen_dc:
        raise ScreenCaptureError("Windows could not access the desktop.")

    memory_dc = None
    bitmap = None
    previous_object = None
    try:
        memory_dc = gdi32.CreateCompatibleDC(screen_dc)
        if not memory_dc:
            raise ScreenCaptureError("Windows could not create a capture context.")

        bitmap = gdi32.CreateCompatibleBitmap(
            screen_dc,
            bounds.width,
            bounds.height,
        )
        if not bitmap:
            raise ScreenCaptureError("Windows could not allocate the screen image.")

        previous_object = gdi32.SelectObject(memory_dc, bitmap)
        if not previous_object:
            raise ScreenCaptureError("Windows could not prepare the screen image.")

        copy_arguments = (
            memory_dc,
            0,
            0,
            bounds.width,
            bounds.height,
            screen_dc,
            bounds.left,
            bounds.top,
        )
        copied = gdi32.BitBlt(*copy_arguments, SRCCOPY | CAPTUREBLT)
        if not copied:
            # Some display drivers reject CAPTUREBLT. Standard SRCCOPY still
            # captures the normal desktop and is sufficient for visible QR codes.
            copied = gdi32.BitBlt(*copy_arguments, SRCCOPY)
        if not copied:
            raise ScreenCaptureError("Windows could not copy the desktop image.")

        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = bounds.width
        bitmap_info.bmiHeader.biHeight = -bounds.height
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = BI_RGB

        pixel_buffer = (ctypes.c_ubyte * (bounds.width * bounds.height * 4))()
        rows = gdi32.GetDIBits(
            memory_dc,
            bitmap,
            0,
            bounds.height,
            pixel_buffer,
            ctypes.byref(bitmap_info),
            DIB_RGB_COLORS,
        )
        if rows != bounds.height:
            raise ScreenCaptureError("Windows returned an incomplete screen image.")

        bgra = np.frombuffer(pixel_buffer, dtype=np.uint8).reshape(
            bounds.height,
            bounds.width,
            4,
        )
        return bgra[:, :, :3].copy()
    finally:
        if previous_object and memory_dc:
            gdi32.SelectObject(memory_dc, previous_object)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory_dc:
            gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(None, screen_dc)


def capture_display(display: ConnectedDisplay) -> np.ndarray:
    """Capture one selected physical display."""

    return capture_screen_bounds(display.bounds)


def capture_virtual_screen() -> np.ndarray:
    """Capture all connected displays as a BGR image held only in memory."""

    if os.name != "nt":
        raise ScreenCaptureError("Screen scanning currently supports Windows only.")
    user32 = ctypes.windll.user32
    _enable_dpi_awareness(user32)
    return capture_screen_bounds(virtual_screen_bounds(user32.GetSystemMetrics))
