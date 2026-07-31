from __future__ import annotations

import time
import unittest

import numpy as np

from bridge.protocol import (
    create_pc_pairing_session,
    random_b64url,
)
from pairing_ui import (
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    build_pairing_canvas,
    generate_pairing_qr_image,
    pairing_seconds_remaining,
)
from qr_reader import QRReader


class PairingUiTests(unittest.TestCase):
    def test_countdown_uses_ceiling_and_never_becomes_negative(self) -> None:
        self.assertEqual(pairing_seconds_remaining(102, now=100.1), 2)
        self.assertEqual(pairing_seconds_remaining(100, now=100), 0)
        self.assertEqual(pairing_seconds_remaining(99, now=100), 0)

    def test_displayed_pairing_qr_decodes_to_the_exact_sensitive_uri(
        self,
    ) -> None:
        now = int(time.time())
        session = create_pc_pairing_session(
            relay_origin="http://127.0.0.1:8765",
            device_id=random_b64url(16),
            receiver_token=random_b64url(32),
            pairing_id=random_b64url(16),
            pairing_token=random_b64url(32),
            expires_at=now + 120,
            now=now,
        )
        image = np.asarray(generate_pairing_qr_image(session.pairing_uri))

        results = QRReader().scan(image)

        self.assertEqual([result.data for result in results], [session.pairing_uri])

    def test_pairing_qr_is_never_written_to_a_file(self) -> None:
        image = generate_pairing_qr_image("wqrs://pair?test=memory-only")
        self.assertEqual(image.size, (360, 360))
        self.assertEqual(image.mode, "RGB")

    def test_packaged_canvas_keeps_pairing_qr_decodable(self) -> None:
        now = int(time.time())
        session = create_pc_pairing_session(
            relay_origin="http://127.0.0.1:8765",
            device_id=random_b64url(16),
            receiver_token=random_b64url(32),
            pairing_id=random_b64url(16),
            pairing_token=random_b64url(32),
            expires_at=now + 120,
            now=now,
        )
        canvas = build_pairing_canvas(
            generate_pairing_qr_image(session.pairing_uri),
            remaining_seconds=120,
            relay_origin=session.qr.relay_origin,
            development_mode=True,
        )

        self.assertEqual(canvas.shape, (WINDOW_HEIGHT, WINDOW_WIDTH, 3))
        results = QRReader().scan_all(canvas)
        self.assertIn(session.pairing_uri, {result.data for result in results})


if __name__ == "__main__":
    unittest.main()
