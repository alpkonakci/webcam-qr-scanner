from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from protocol.generate_vectors import (
    OUTPUT_PATH,
    b64url_encode,
    build_vector,
    canonical_json,
    serialized_vector,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIRECTORY = ROOT / "protocol" / "schemas"


def decode_base64url(value: str) -> bytes:
    import base64

    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class ProtocolSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vector = json.loads(OUTPUT_PATH.read_text("utf-8"))
        cls.schemas = {
            path.name: json.loads(path.read_text("utf-8"))
            for path in SCHEMA_DIRECTORY.glob("*.schema.json")
        }
        for schema in cls.schemas.values():
            Draft202012Validator.check_schema(schema)

    def validate(self, schema_name: str, instance: dict) -> None:
        Draft202012Validator(self.schemas[schema_name]).validate(instance)

    def test_committed_vector_matches_generator(self) -> None:
        self.assertEqual(OUTPUT_PATH.read_text("utf-8"), serialized_vector())

    def test_pairing_transcript_matches_schema(self) -> None:
        self.validate(
            "pairing-transcript.schema.json",
            self.vector["derived"]["pairing_transcript"],
        )

    def test_pairing_uri_has_exact_single_value_parameters(self) -> None:
        parsed = urlsplit(self.vector["derived"]["pairing_uri"])
        self.assertEqual(parsed.scheme, "wqrs")
        self.assertEqual(parsed.netloc, "pair")
        self.assertEqual(parsed.path, "")
        self.assertEqual(parsed.fragment, "")
        parameters = parse_qs(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
        )
        self.assertEqual(
            set(parameters),
            {
                "v",
                "relay",
                "device",
                "pairing",
                "pairing_token",
                "pc_key",
                "secret",
                "expires",
            },
        )
        self.assertTrue(all(len(values) == 1 for values in parameters.values()))
        self.assertEqual(parameters["v"], ["1"])
        self.assertEqual(parameters["relay"], ["https://relay.example"])
        self.assertEqual(parameters["device"], [self.vector["inputs"]["device_id"]])
        self.assertEqual(
            parameters["pairing"],
            [self.vector["inputs"]["pairing_id"]],
        )
        self.assertEqual(
            parameters["pairing_token"],
            [self.vector["inputs"]["pairing_relay_token"]],
        )
        self.assertEqual(
            parameters["pc_key"],
            [self.vector["derived"]["pc_public_key"]],
        )
        self.assertEqual(
            parameters["secret"],
            [self.vector["inputs"]["pairing_secret"]],
        )

    def test_all_envelopes_match_schema(self) -> None:
        for name, test_case in self.vector["cases"].items():
            with self.subTest(name=name):
                self.validate(
                    "encrypted-envelope.schema.json",
                    test_case["envelope"],
                )

    def test_all_payloads_match_their_schemas(self) -> None:
        cases = self.vector["cases"]
        mapping = {
            "pair_request": "pair-request-payload.schema.json",
            "pair_result": "pair-result-payload.schema.json",
            "url_message": "url-payload.schema.json",
            "delivered_ack": "delivered-ack-payload.schema.json",
        }
        for case_name, schema_name in mapping.items():
            with self.subTest(case=case_name):
                self.validate(schema_name, cases[case_name]["payload"])

    def test_unknown_envelope_field_is_rejected(self) -> None:
        envelope = copy.deepcopy(
            self.vector["cases"]["url_message"]["envelope"],
        )
        envelope["unexpected"] = True
        with self.assertRaises(ValidationError):
            self.validate("encrypted-envelope.schema.json", envelope)

    def test_unsupported_protocol_is_rejected(self) -> None:
        envelope = copy.deepcopy(
            self.vector["cases"]["url_message"]["envelope"],
        )
        envelope["protocol"] = "wqrs/2"
        with self.assertRaises(ValidationError):
            self.validate("encrypted-envelope.schema.json", envelope)

    def test_bad_nonce_and_old_key_epoch_are_rejected(self) -> None:
        envelope = copy.deepcopy(
            self.vector["cases"]["url_message"]["envelope"],
        )
        envelope["nonce"] += "="
        with self.assertRaises(ValidationError):
            self.validate("encrypted-envelope.schema.json", envelope)

        envelope = copy.deepcopy(
            self.vector["cases"]["url_message"]["envelope"],
        )
        envelope["key_epoch"] = 0
        with self.assertRaises(ValidationError):
            self.validate("encrypted-envelope.schema.json", envelope)

    def test_approved_pair_result_requires_sender_token(self) -> None:
        payload = copy.deepcopy(self.vector["cases"]["pair_result"]["payload"])
        del payload["sender_token"]
        with self.assertRaises(ValidationError):
            self.validate("pair-result-payload.schema.json", payload)


class ProtocolCryptoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vector = build_vector()

    def decrypt_case(self, case_name: str, key_name: str) -> bytes:
        test_case = self.vector["cases"][case_name]
        envelope = test_case["envelope"]
        ciphertext = decode_base64url(envelope["ciphertext"])
        nonce = decode_base64url(envelope["nonce"])
        aad_fields = {
            key: value
            for key, value in envelope.items()
            if key != "ciphertext"
        }
        key = decode_base64url(self.vector["derived"][key_name])
        return AESGCM(key).decrypt(
            nonce,
            ciphertext,
            canonical_json(aad_fields),
        )

    def test_all_cases_decrypt_to_canonical_payload(self) -> None:
        key_mapping = {
            "pair_request": "handshake_key",
            "pair_result": "handshake_key",
            "url_message": "message_key",
            "delivered_ack": "ack_key",
        }
        for case_name, key_name in key_mapping.items():
            with self.subTest(case=case_name):
                plaintext = self.decrypt_case(case_name, key_name)
                self.assertEqual(
                    plaintext,
                    canonical_json(self.vector["cases"][case_name]["payload"]),
                )

    def test_tampered_ciphertext_is_rejected(self) -> None:
        test_case = copy.deepcopy(self.vector["cases"]["url_message"])
        envelope = test_case["envelope"]
        ciphertext = bytearray(decode_base64url(envelope["ciphertext"]))
        ciphertext[0] ^= 1
        envelope["ciphertext"] = b64url_encode(bytes(ciphertext))
        nonce = decode_base64url(envelope["nonce"])
        aad_fields = {
            key: value
            for key, value in envelope.items()
            if key != "ciphertext"
        }
        key = decode_base64url(self.vector["derived"]["message_key"])

        with self.assertRaises(InvalidTag):
            AESGCM(key).decrypt(
                nonce,
                bytes(ciphertext),
                canonical_json(aad_fields),
            )

    def test_modified_associated_data_is_rejected(self) -> None:
        test_case = self.vector["cases"]["url_message"]
        envelope = test_case["envelope"]
        ciphertext = decode_base64url(envelope["ciphertext"])
        nonce = decode_base64url(envelope["nonce"])
        aad_fields = {
            key: value
            for key, value in envelope.items()
            if key != "ciphertext"
        }
        aad_fields["expires_at"] += 1
        key = decode_base64url(self.vector["derived"]["message_key"])

        with self.assertRaises(InvalidTag):
            AESGCM(key).decrypt(
                nonce,
                ciphertext,
                canonical_json(aad_fields),
            )

    def test_message_and_ack_keys_are_separate(self) -> None:
        self.assertNotEqual(
            self.vector["derived"]["message_key"],
            self.vector["derived"]["ack_key"],
        )

    def test_canonical_json_rejects_floats_and_non_ascii_keys(self) -> None:
        with self.assertRaises(TypeError):
            canonical_json({"value": 1.5})
        with self.assertRaises(TypeError):
            canonical_json({"değer": 1})


if __name__ == "__main__":
    unittest.main()
