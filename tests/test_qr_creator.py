from __future__ import annotations

import io
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np
from PIL import Image

from clipboard_support import _write_clipboard, copy_image, copy_text, image_to_dib
from qr_creator import MAX_CREATE_BYTES, create_qr, validate_creation_value


class QrCreatorTests(unittest.TestCase):
    def test_generated_link_round_trips_without_opening_or_network(self):
        value = "https://example.com/video?id=42&name=test"
        qr = create_qr("  " + value + "  ")
        decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(np.asarray(qr.image))
        self.assertEqual(qr.value, value)
        self.assertEqual(qr.kind, "link")
        self.assertEqual(decoded, value)

    def test_turkish_emoji_and_multiline_text_round_trip(self):
        value = "  Merhaba dünya! Çığ, şükran, İ 😀\nİkinci satır\tson  "
        qr = create_qr(value, "text")
        decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(np.asarray(qr.image))
        self.assertEqual(decoded, value)
        self.assertEqual(qr.value, value)

    def test_quiet_zone_and_lossless_png_export(self):
        qr = create_qr("https://example.com/")
        pixels = np.asarray(qr.image)
        black = np.where(pixels[:, :, 0] == 0)
        border = int(black[0].min())
        self.assertGreaterEqual(border, 4 * 4)
        self.assertTrue(np.all(pixels[:border] == 255))
        output = io.BytesIO()
        qr.image.save(output, format="PNG")
        output.seek(0)
        restored = Image.open(output)
        self.assertEqual(restored.size, qr.image.size)
        self.assertTrue(np.array_equal(np.asarray(restored), pixels))

    def test_byte_limit_is_not_a_character_limit(self):
        self.assertEqual(validate_creation_value("a" * MAX_CREATE_BYTES, "text"), "a" * MAX_CREATE_BYTES)
        for value in ("a" * (MAX_CREATE_BYTES + 1), "ü" * 301):
            with self.subTest(value_length=len(value)), self.assertRaises(ValueError):
                create_qr(value, "text")

    def test_invalid_links_and_control_characters_are_rejected(self):
        for value in ("example.com", "javascript:alert(1)", "file:///C:/x", "https://u:p@example.com",
                      "https://example.com:99999", "https://example.com/a b", "https://", "\x00"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                create_qr(value)
        for value in ("", "  ", "hi\x00there", "hi\x7fthere", "\ud800"):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                create_qr(value, "text")

    def test_html_and_commands_are_only_encoded_as_text(self):
        value = "<script>alert(1)</script>\npowershell Remove-Item file"
        qr = create_qr(value, "text")
        decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(np.asarray(qr.image))
        self.assertEqual(decoded, value)


class ClipboardTests(unittest.TestCase):
    def test_text_format_is_terminated_unicode_with_explicit_window_owner(self):
        with patch("clipboard_support._write_clipboard") as write:
            copy_text("Türkçe 😀", owner=123)
        write.assert_called_once_with("Türkçe 😀".encode("utf-16-le") + b"\0\0", 13, 123)

    def test_null_text_never_changes_clipboard(self):
        with patch("clipboard_support._write_clipboard") as write, self.assertRaises(ValueError):
            copy_text("a\0b", owner=123)
        write.assert_not_called()

    def test_image_clipboard_contains_dib_not_bmp_header(self):
        image = Image.new("RGB", (10, 7), "white")
        dib = image_to_dib(image)
        self.assertEqual(int.from_bytes(dib[:4], "little"), 40)
        self.assertEqual(int.from_bytes(dib[4:8], "little"), 10)
        with patch("clipboard_support._write_clipboard") as write:
            copy_image(image, owner=321)
        write.assert_called_once_with(dib, 8, 321)

    def test_clipboard_transfer_uses_owner_and_windows_owns_successful_memory(self):
        user32, kernel32 = Mock(), Mock()
        kernel32.GlobalAlloc.return_value = 123
        kernel32.GlobalLock.return_value = 456
        user32.OpenClipboard.return_value = True
        user32.EmptyClipboard.return_value = True
        user32.SetClipboardData.return_value = 123
        with patch("clipboard_support.os.name", "nt"), patch("clipboard_support.ctypes.windll.user32", user32), \
                patch("clipboard_support.ctypes.windll.kernel32", kernel32), patch("clipboard_support.ctypes.memmove"):
            _write_clipboard(b"test", 13, 999)
        user32.OpenClipboard.assert_called_once_with(999)
        user32.CloseClipboard.assert_called_once_with()
        kernel32.GlobalFree.assert_not_called()

    def test_busy_clipboard_frees_memory_without_emptying_it(self):
        user32, kernel32 = Mock(), Mock()
        kernel32.GlobalAlloc.return_value = 123
        kernel32.GlobalLock.return_value = 456
        user32.OpenClipboard.return_value = False
        with patch("clipboard_support.os.name", "nt"), patch("clipboard_support.ctypes.windll.user32", user32), \
                patch("clipboard_support.ctypes.windll.kernel32", kernel32), patch("clipboard_support.ctypes.memmove"), \
                self.assertRaises(OSError):
            _write_clipboard(b"test", 13, 999)
        user32.EmptyClipboard.assert_not_called()
        user32.CloseClipboard.assert_not_called()
        kernel32.GlobalFree.assert_called_once_with(123)

    def test_missing_owner_is_rejected_before_allocation(self):
        with patch("clipboard_support.ctypes.windll.kernel32") as kernel32, self.assertRaises(OSError):
            _write_clipboard(b"test", 13, 0)
        kernel32.GlobalAlloc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
