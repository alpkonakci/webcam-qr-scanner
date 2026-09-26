import unittest

import cv2
import numpy as np

from qr_reader import QRReader


def make_qr_code(value: str) -> np.ndarray:
    encoder = cv2.QRCodeEncoder_create()
    image = encoder.encode(value)
    image = cv2.copyMakeBorder(
        image,
        4,
        4,
        4,
        4,
        cv2.BORDER_CONSTANT,
        value=255,
    )
    return cv2.resize(image, None, fx=10, fy=10, interpolation=cv2.INTER_NEAREST)


class QRReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reader = QRReader()

    def test_reads_generated_qr_code(self) -> None:
        results = self.reader.scan(make_qr_code("https://example.com/test"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].data, "https://example.com/test")
        self.assertEqual(results[0].corners.shape, (4, 2))

    def test_returns_empty_list_when_no_qr_exists(self) -> None:
        blank_image = np.full((300, 300, 3), 255, dtype=np.uint8)

        self.assertEqual(self.reader.scan(blank_image), [])

    def test_returns_empty_list_for_empty_frame(self) -> None:
        empty_image = np.array([], dtype=np.uint8)

        self.assertEqual(self.reader.scan(empty_image), [])

    def test_reads_qr_after_phone_screen_resampling(self) -> None:
        qr_image = make_qr_code("https://example.com/mobile")
        large_frame = cv2.resize(
            qr_image,
            (1400, 1400),
            interpolation=cv2.INTER_NEAREST,
        )
        # Fine bright lines approximate mild interference from a display panel.
        bright_lines = large_frame[::8, :].astype(np.int16) + 18
        large_frame[::8, :] = np.clip(bright_lines, 0, 255).astype(np.uint8)

        results = self.reader.scan(large_frame)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].data, "https://example.com/mobile")

    def test_screen_scan_finds_codes_overlooked_by_first_multi_pass(self) -> None:
        frame = np.full((720, 1280, 3), 255, dtype=np.uint8)
        values = (
            "https://example.com/one",
            "https://example.com/two",
        )
        for value, (left, top) in zip(
            values,
            ((160, 220), (820, 220)),
        ):
            qr_image = cv2.resize(
                make_qr_code(value),
                (260, 260),
                interpolation=cv2.INTER_NEAREST,
            )
            frame[top : top + 260, left : left + 260] = cv2.cvtColor(
                qr_image,
                cv2.COLOR_GRAY2BGR,
            )

        results = self.reader.scan_all(frame)

        self.assertEqual({result.data for result in results}, set(values))


if __name__ == "__main__":
    unittest.main()
