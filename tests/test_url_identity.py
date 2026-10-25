"""Confirmation and navigation must identify the same browser destination."""
import unittest
from unittest.mock import patch

from app import confirm_screen_url
from bridge.protocol import ProtocolViolation, validate_url
from links import open_web_url


class UrlIdentityTests(unittest.TestCase):
    def test_unicode_hosts_are_canonicalized_before_display_and_open(self):
        for original, expected, host in (
            ("https://faß.de/ç?q=ışık#ş", "https://xn--fa-hia.de/ç?q=ışık#ş", "xn--fa-hia.de"),
            ("https://ς.gr/", "https://xn--3xa.gr/", "xn--3xa.gr"),
            ("https://bücher.example/path", "https://xn--bcher-kva.example/path", "xn--bcher-kva.example"),
        ):
            with self.subTest(original=original):
                url, displayed, secure = validate_url(original)
                self.assertEqual((url, displayed, secure), (expected, host, True))
                with patch("links.webbrowser.open", return_value=True) as browser:
                    self.assertTrue(open_web_url(original))
                    self.assertEqual(browser.call_args.args[0], expected)
                with patch("app.show_dialog", return_value=6) as dialog:
                    self.assertTrue(confirm_screen_url(original))
                    self.assertIn(f"Website:\n{host}\n", dialog.call_args.args[1])
                    self.assertIn(expected, dialog.call_args.args[1])

    def test_ambiguous_hosts_never_reach_browser_or_confirmation(self):
        for host in ("a\u200db.example", "a\u200cb.example", "%65xample.com", "2130706433", "0177.0.0.1", "0x7f000001"):
            value = f"https://{host}/"
            with self.subTest(host=host):
                with self.assertRaises(ProtocolViolation):
                    validate_url(value)
                with patch("links.webbrowser.open") as browser, patch("app.show_dialog") as dialog:
                    self.assertFalse(open_web_url(value))
                    self.assertFalse(confirm_screen_url(value))
                    browser.assert_not_called()
                    dialog.assert_not_called()

    def test_canonical_ascii_ip_and_ports_remain_usable(self):
        for value, expected, host in (
            ("https://EXAMPLE.com:8443/a", "https://example.com:8443/a", "example.com"),
            ("http://127.0.0.1:8080/a", "http://127.0.0.1:8080/a", "127.0.0.1"),
            ("https://[2001:db8::1]:8443/a", "https://[2001:db8::1]:8443/a", "2001:db8::1"),
            ("https://[::ffff:192.0.2.128]/", "https://[::ffff:c000:280]/", "::ffff:c000:280"),
        ):
            with self.subTest(value=value):
                self.assertEqual(validate_url(value)[:2], (expected, host))


if __name__ == "__main__":
    unittest.main()
