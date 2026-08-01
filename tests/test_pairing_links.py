from __future__ import annotations

import time
import unittest

from bridge.pairing_links import (
    PUBLIC_SERVICE_ORIGIN,
    build_pairing_launch_url,
    extract_pairing_uri,
)
from bridge.protocol import create_pc_pairing_session, random_b64url


class PairingLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        now = int(time.time())
        self.session = create_pc_pairing_session(
            relay_origin=PUBLIC_SERVICE_ORIGIN,
            device_id=random_b64url(16),
            receiver_token=random_b64url(32),
            pairing_id=random_b64url(16),
            pairing_token=random_b64url(32),
            expires_at=now + 120,
            now=now,
        )

    def test_https_launch_keeps_pairing_material_in_the_fragment(self) -> None:
        launch_url = build_pairing_launch_url(self.session.pairing_uri)

        self.assertTrue(launch_url.startswith(f"{PUBLIC_SERVICE_ORIGIN}/#"))
        self.assertNotIn("?", launch_url.split("#", 1)[0])
        self.assertEqual(
            extract_pairing_uri(launch_url),
            self.session.pairing_uri,
        )

    def test_direct_wqrs_uri_remains_available_for_local_tests(self) -> None:
        self.assertEqual(
            extract_pairing_uri(self.session.pairing_uri),
            self.session.pairing_uri,
        )

    def test_untrusted_web_origin_cannot_wrap_a_pairing_uri(self) -> None:
        value = f"https://example.com/#{self.session.pairing_uri}"

        with self.assertRaisesRegex(ValueError, "invalid"):
            extract_pairing_uri(value)


if __name__ == "__main__":
    unittest.main()
