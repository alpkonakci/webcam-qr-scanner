from __future__ import annotations

import copy
import time
import unittest
from unittest.mock import patch

from bridge.protocol import (
    AuthenticationFailed,
    MAX_CLOCK_SKEW_SECONDS,
    PAIRING_TTL_SECONDS,
    ProtocolViolation,
    ReplayDetected,
    ReceiverCredentials,
    SenderCredentials,
    approve_pairing_request,
    b64url_decode,
    build_delivery_ack,
    build_url_envelope,
    canonical_json,
    create_pc_pairing_session,
    create_phone_pairing_attempt,
    create_local_pairing,
    decrypt_pairing_request,
    decrypt_pairing_result,
    decrypt_url_envelope,
    parse_pairing_uri,
    random_b64url,
    reject_pairing_request,
    validate_url,
    verify_delivery_ack,
)
from bridge.replay import InMemoryReplayGuard
from native_dialogs import (
    MB_DEFBUTTON2,
    MB_ICONWARNING,
    MB_SETFOREGROUND,
    MB_TOPMOST,
    MB_YESNO,
    confirm_phone_pairing,
    confirm_phone_url,
    show_dialog,
)


def paired_credentials() -> tuple[ReceiverCredentials, SenderCredentials]:
    device_id = random_b64url(16)
    receiver_token = random_b64url(32)
    pairing = create_local_pairing(
        relay_origin="http://127.0.0.1:8765",
        device_id=device_id,
        receiver_token=receiver_token,
        now=1_785_100_000,
    )
    return pairing.receiver, pairing.sender


class PhoneToPcCryptoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receiver, self.sender = paired_credentials()
        self.now = int(time.time())

    def test_pairing_derives_the_same_root_key_on_both_sides(self) -> None:
        self.assertEqual(self.receiver.root_key, self.sender.root_key)
        self.assertEqual(len(self.receiver.root_key), 32)
        self.assertEqual(self.receiver.pair_id, self.sender.pair_id)

    def test_pairing_uses_fresh_random_credentials(self) -> None:
        other_receiver, other_sender = paired_credentials()
        self.assertNotEqual(self.receiver.pair_id, other_receiver.pair_id)
        self.assertNotEqual(self.sender.sender_token, other_sender.sender_token)
        self.assertNotEqual(self.receiver.root_key, other_receiver.root_key)

    def test_valid_message_and_ack_complete_the_crypto_round_trip(self) -> None:
        envelope = build_url_envelope(
            self.sender,
            "https://example.com/path?q=qr",
            now=self.now,
        )
        received = decrypt_url_envelope(
            self.receiver,
            envelope,
            replay_guard=InMemoryReplayGuard(),
            now=self.now,
        )
        self.assertEqual(received.url, "https://example.com/path?q=qr")
        self.assertEqual(received.hostname_ascii, "example.com")
        self.assertTrue(received.is_secure)

        acknowledgement = build_delivery_ack(
            self.receiver,
            received.message_id,
            now=self.now,
        )
        verify_delivery_ack(
            self.sender,
            acknowledgement,
            expected_message_id=received.message_id,
            now=self.now,
        )

    def test_modified_ciphertext_is_rejected_without_consuming_message_id(
        self,
    ) -> None:
        envelope = build_url_envelope(
            self.sender,
            "https://example.com/tamper-test",
            now=self.now,
        )
        tampered = copy.deepcopy(envelope)
        replacement = "A" if tampered["ciphertext"][-1] != "A" else "B"
        tampered["ciphertext"] = tampered["ciphertext"][:-1] + replacement
        guard = InMemoryReplayGuard()

        with self.assertRaises(AuthenticationFailed):
            decrypt_url_envelope(
                self.receiver,
                tampered,
                replay_guard=guard,
                now=self.now,
            )
        received = decrypt_url_envelope(
            self.receiver,
            envelope,
            replay_guard=guard,
            now=self.now,
        )
        self.assertEqual(received.message_id, envelope["message_id"])

    def test_repeated_authenticated_message_is_rejected(self) -> None:
        envelope = build_url_envelope(
            self.sender,
            "https://example.com/replay-test",
            now=self.now,
        )
        guard = InMemoryReplayGuard()
        decrypt_url_envelope(
            self.receiver,
            envelope,
            replay_guard=guard,
            now=self.now,
        )
        with self.assertRaises(ReplayDetected):
            decrypt_url_envelope(
                self.receiver,
                envelope,
                replay_guard=guard,
                now=self.now,
            )

    def test_expired_message_is_rejected(self) -> None:
        envelope = build_url_envelope(
            self.sender,
            "https://example.com/expired",
            now=self.now - 301,
        )
        with self.assertRaisesRegex(ProtocolViolation, "expired"):
            decrypt_url_envelope(
                self.receiver,
                envelope,
                replay_guard=InMemoryReplayGuard(),
                now=self.now,
            )

    def test_ack_cannot_be_verified_with_the_message_key_or_another_pair(
        self,
    ) -> None:
        envelope = build_url_envelope(
            self.sender,
            "https://example.com",
            now=self.now,
        )
        acknowledgement = build_delivery_ack(
            self.receiver,
            envelope["message_id"],
            now=self.now,
        )
        _, other_sender = paired_credentials()
        with self.assertRaises(ProtocolViolation):
            verify_delivery_ack(
                other_sender,
                acknowledgement,
                expected_message_id=envelope["message_id"],
                now=self.now,
            )

    def test_base64url_decoder_is_strict(self) -> None:
        value = random_b64url(16)
        self.assertEqual(len(b64url_decode(value, expected_length=16)), 16)
        with self.assertRaises(ProtocolViolation):
            b64url_decode(value + "=", expected_length=16)

    def test_canonical_json_rejects_floats(self) -> None:
        with self.assertRaises(ProtocolViolation):
            canonical_json({"value": 1.5})


class PhoneToPcPairingProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 1_785_100_000
        self.session = create_pc_pairing_session(
            relay_origin="http://127.0.0.1:8765",
            device_id=random_b64url(16),
            receiver_token=random_b64url(32),
            pairing_id=random_b64url(16),
            pairing_token=random_b64url(32),
            expires_at=self.now + 120,
            now=self.now,
        )
        self.phone = create_phone_pairing_attempt(
            self.session.pairing_uri,
            phone_label="My iPhone",
            now=self.now,
        )

    def test_relay_pairing_accepts_bounded_clock_skew(self) -> None:
        session = create_pc_pairing_session(
            relay_origin="https://relay.example",
            device_id=random_b64url(16),
            receiver_token=random_b64url(32),
            pairing_id=random_b64url(16),
            pairing_token=random_b64url(32),
            expires_at=self.now + PAIRING_TTL_SECONDS + 1,
            now=self.now,
        )

        self.assertEqual(
            session.qr.expires_at,
            self.now + PAIRING_TTL_SECONDS + 1,
        )

    def test_relay_pairing_rejects_excessive_lifetime(self) -> None:
        with self.assertRaisesRegex(ProtocolViolation, "too long"):
            create_pc_pairing_session(
                relay_origin="https://relay.example",
                device_id=random_b64url(16),
                receiver_token=random_b64url(32),
                pairing_id=random_b64url(16),
                pairing_token=random_b64url(32),
                expires_at=(
                    self.now
                    + PAIRING_TTL_SECONDS
                    + MAX_CLOCK_SKEW_SECONDS
                    + 1
                ),
                now=self.now,
            )

    def test_approved_pairing_derives_matching_credentials(self) -> None:
        request = decrypt_pairing_request(
            self.session,
            self.phone.request_envelope,
            now=self.now,
        )
        approval = approve_pairing_request(
            self.session,
            request,
            pc_label="Home PC",
            now=self.now,
        )
        sender = decrypt_pairing_result(
            self.phone,
            approval.result_envelope,
            now=self.now,
        )

        self.assertIsNotNone(sender)
        assert sender is not None
        self.assertEqual(request.phone_label, "My iPhone")
        self.assertEqual(approval.receiver.pair_id, sender.pair_id)
        self.assertEqual(approval.receiver.root_key, sender.root_key)
        self.assertEqual(approval.sender_token, sender.sender_token)

    def test_rejection_creates_no_sender_credentials(self) -> None:
        request = decrypt_pairing_request(
            self.session,
            self.phone.request_envelope,
            now=self.now,
        )
        rejection = reject_pairing_request(
            self.session,
            request,
            now=self.now,
        )
        self.assertIsNone(
            decrypt_pairing_result(
                self.phone,
                rejection,
                now=self.now,
            )
        )

    def test_tampered_pairing_request_fails_authentication(self) -> None:
        tampered = copy.deepcopy(self.phone.request_envelope)
        replacement = "A" if tampered["ciphertext"][0] != "A" else "B"
        tampered["ciphertext"] = replacement + tampered["ciphertext"][1:]
        with self.assertRaises(AuthenticationFailed):
            decrypt_pairing_request(
                self.session,
                tampered,
                now=self.now,
            )

    def test_pairing_uri_rejects_duplicate_and_expired_values(self) -> None:
        with self.assertRaisesRegex(ProtocolViolation, "exactly once"):
            parse_pairing_uri(
                self.session.pairing_uri + "&device=" + random_b64url(16),
                now=self.now,
            )
        with self.assertRaisesRegex(ProtocolViolation, "expired"):
            parse_pairing_uri(
                self.session.pairing_uri,
                now=self.now + 121,
            )

    def test_pairing_label_is_bounded_and_trimmed(self) -> None:
        for label in ("", " padded ", "x" * 81, "bad\nlabel"):
            with self.subTest(label=label):
                with self.assertRaises(ProtocolViolation):
                    create_phone_pairing_attempt(
                        self.session.pairing_uri,
                        phone_label=label,
                        now=self.now,
                    )


class PhoneToPcUrlValidationTests(unittest.TestCase):
    def test_https_and_unicode_host_are_accepted_with_ascii_display(self) -> None:
        url, hostname, secure = validate_url("https://bücher.example/path")
        self.assertEqual(url, "https://bücher.example/path")
        self.assertEqual(hostname, "xn--bcher-kva.example")
        self.assertTrue(secure)

    def test_http_is_accepted_but_marked_insecure(self) -> None:
        _, _, secure = validate_url("http://example.com")
        self.assertFalse(secure)

    def test_dangerous_or_ambiguous_urls_are_rejected(self) -> None:
        invalid_values = (
            "javascript:alert(1)",
            "file:///C:/Windows",
            "https://user:pass@example.com",
            "https://example.com:99999",
            "https://example.com/\nnext",
            " https://example.com",
            "https://example.com\\@attacker.test",
            "https://" + ("a" * 4090) + ".example",
        )
        for value in invalid_values:
            with self.subTest(value=value[:80]):
                with self.assertRaises(ProtocolViolation):
                    validate_url(value)


class PhoneToPcDialogTests(unittest.TestCase):
    @patch("native_dialogs.ctypes.windll")
    def test_native_dialog_is_forced_forward_from_background_threads(
        self,
        windll,
    ) -> None:
        windll.user32.MessageBoxW.return_value = 7

        show_dialog("QR Scanner", "Question", MB_YESNO)

        style = windll.user32.MessageBoxW.call_args.args[3]
        self.assertTrue(style & MB_SETFOREGROUND)
        self.assertTrue(style & MB_TOPMOST)

    @patch("native_dialogs.show_dialog", return_value=6)
    def test_confirmation_shows_ascii_host_and_defaults_to_no(
        self,
        show_dialog,
    ) -> None:
        approved = confirm_phone_url(
            "https://bücher.example/path",
            "xn--bcher-kva.example",
            phone_label="Test phone",
        )
        self.assertTrue(approved)
        title, message, style = show_dialog.call_args.args
        self.assertEqual(title, "QR Scanner - Phone-to-PC")
        self.assertIn("Test phone", message)
        self.assertIn("xn--bcher-kva.example", message)
        self.assertEqual(
            style,
            MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2,
        )

    @patch("native_dialogs.show_dialog", return_value=7)
    def test_pairing_confirmation_defaults_to_reject(
        self,
        show_dialog,
    ) -> None:
        approved = confirm_phone_pairing(
            "My iPhone",
            relay_origin="https://relay.example",
        )
        self.assertFalse(approved)
        title, message, style = show_dialog.call_args.args
        self.assertEqual(title, "QR Scanner - Pair Phone")
        self.assertIn("My iPhone", message)
        self.assertIn("Mobile PWA", message)
        self.assertIn("https://relay.example", message)
        self.assertEqual(
            style,
            MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2,
        )


if __name__ == "__main__":
    unittest.main()
