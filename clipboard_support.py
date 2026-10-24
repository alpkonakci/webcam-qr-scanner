"""Explicit, user-triggered Windows clipboard writes; no background reads."""

from __future__ import annotations

import ctypes
import io
import os

from PIL import Image


def image_to_dib(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="BMP")
    return buffer.getvalue()[14:]  # CF_DIB does not include the BMP file header.


def _write_clipboard(data: bytes, clipboard_format: int, owner: int) -> None:
    if os.name != "nt":
        raise OSError("Clipboard copying is available on Windows.")
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    kernel32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalFree.restype = ctypes.c_void_p
    user32.OpenClipboard.argtypes = (ctypes.c_void_p,)
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)
    user32.SetClipboardData.restype = ctypes.c_void_p
    if not owner:
        raise OSError("Open the QR window before copying.")
    handle = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
    if not handle:
        raise OSError("Clipboard memory could not be allocated.")
    opened = False
    try:
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise OSError("Clipboard memory could not be locked.")
        try:
            ctypes.memmove(pointer, data, len(data))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.OpenClipboard(owner):
            raise OSError("The clipboard is busy. Try again.")
        opened = True
        if not user32.EmptyClipboard():
            raise OSError(f"The clipboard could not be cleared (Windows error {kernel32.GetLastError()}).")
        if not user32.SetClipboardData(clipboard_format, handle):
            raise OSError(f"The QR could not be copied (Windows error {kernel32.GetLastError()}).")
        handle = None  # Windows owns the allocation after SetClipboardData.
    finally:
        if opened:
            user32.CloseClipboard()
        if handle:
            kernel32.GlobalFree(handle)


def copy_text(value: str, *, owner: int) -> None:
    if "\x00" in value:
        raise ValueError("Text contains an unsupported null character.")
    _write_clipboard(value.encode("utf-16-le") + b"\x00\x00", 13, owner)


def copy_image(image: Image.Image, *, owner: int) -> None:
    _write_clipboard(image_to_dib(image), 8, owner)
