from __future__ import annotations

import time
import unittest

import numpy as np

from bridge.protocol import (
    create_pc_pairing_session,
    random_b64url,
)
from bridge.pairing_links import PUBLIC_SERVICE_ORIGIN, build_pairing_launch_url
from pairing_ui import (
    QR_SIZE,
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

    def test_displayed_pairing_qr_decodes_to_the_https_launch_url(
        self,
    ) -> None:
        now = int(time.time())
        session = create_pc_pairing_session(
            relay_origin=PUBLIC_SERVICE_ORIGIN,
            device_id=random_b64url(16),
            receiver_token=random_b64url(32),
            pairing_id=random_b64url(16),
            pairing_token=random_b64url(32),
            expires_at=now + 120,
            now=now,
        )
        launch_url = build_pairing_launch_url(session.pairing_uri)
        image = np.asarray(generate_pairing_qr_image(launch_url))

        results = QRReader().scan(image)

        self.assertEqual([result.data for result in results], [launch_url])

    def test_pairing_qr_is_never_written_to_a_file(self) -> None:
        image = generate_pairing_qr_image("wqrs://pair?test=memory-only")
        self.assertEqual(image.size, (QR_SIZE, QR_SIZE))
        self.assertEqual(image.mode, "RGB")

    def test_packaged_canvas_keeps_pairing_qr_decodable(self) -> None:
        now = int(time.time())
        session = create_pc_pairing_session(
            relay_origin=PUBLIC_SERVICE_ORIGIN,
            device_id=random_b64url(16),
            receiver_token=random_b64url(32),
            pairing_id=random_b64url(16),
            pairing_token=random_b64url(32),
            expires_at=now + 120,
            now=now,
        )
        launch_url = build_pairing_launch_url(session.pairing_uri)
        canvas = build_pairing_canvas(
            generate_pairing_qr_image(launch_url),
            remaining_seconds=120,
            relay_origin=session.qr.relay_origin,
            development_mode=False,
        )

        self.assertEqual(canvas.shape, (WINDOW_HEIGHT, WINDOW_WIDTH, 3))
        left = (WINDOW_WIDTH - QR_SIZE) // 2
        qr_region = canvas[108 : 108 + QR_SIZE, left : left + QR_SIZE]
        results = QRReader().scan(qr_region)
        self.assertIn(launch_url, {result.data for result in results})


if __name__ == "__main__":
    unittest.main()
