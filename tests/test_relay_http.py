from __future__ import annotations

import unittest

from bridge.relay_http import (
    BYPASS_HEADER,
    BYPASS_ORIGIN_ENV,
    BYPASS_SECRET_ENV,
    relay_protection_headers,
)


PREVIEW = "https://webcam-qr-scanner-example.vercel.app"
SECRET = "temporary-preview-access"


class RelayProtectionHeaderTests(unittest.TestCase):
    def test_unconfigured_client_sends_no_bypass_header(self) -> None:
        self.assertEqual(relay_protection_headers(PREVIEW, {}), {})

    def test_secret_is_only_sent_to_exact_preview_origin(self) -> None:
        environment = {
            BYPASS_ORIGIN_ENV: PREVIEW + "/",
            BYPASS_SECRET_ENV: SECRET,
        }
        self.assertEqual(
            relay_protection_headers(PREVIEW, environment),
            {BYPASS_HEADER: SECRET},
        )
        for other_origin in (
            "https://another.vercel.app",
            "https://webcam-qr-scanner-example.vercel.app.evil.example",
            "https://project.supabase.co",
            "http://127.0.0.1:8765",
        ):
            with self.subTest(origin=other_origin):
                self.assertEqual(relay_protection_headers(other_origin, environment), {})

    def test_incomplete_configuration_fails_without_echoing_secret(self) -> None:
        for environment in (
            {BYPASS_ORIGIN_ENV: PREVIEW},
            {BYPASS_SECRET_ENV: SECRET},
        ):
            with self.subTest(environment=tuple(environment)):
                with self.assertRaises(ValueError) as caught:
                    relay_protection_headers(PREVIEW, environment)
                self.assertNotIn(SECRET, str(caught.exception))

    def test_invalid_target_or_secret_fails_closed(self) -> None:
        for target in ("http://example.vercel.app", "https://example.com"):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    relay_protection_headers(
                        PREVIEW,
                        {BYPASS_ORIGIN_ENV: target, BYPASS_SECRET_ENV: SECRET},
                    )
        with self.assertRaises(ValueError):
            relay_protection_headers(
                PREVIEW,
                {BYPASS_ORIGIN_ENV: PREVIEW, BYPASS_SECRET_ENV: "bad\r\nheader"},
            )
