# WQRS/1 protocol contract

This directory is the version-controlled, language-neutral contract for the
Phone-to-PC Bridge planned for Webcam QR Scanner v0.2.

The protocol is not connected to the stable production application yet. Phase
0 fixed the wire format and deterministic conformance vectors. The current
`v0.2.0-dev` source exercises the same contract through the localhost relay,
the public D1 relay API, the mobile PWA, and the persistent desktop receiver.
One real iPhone-to-Windows flow has passed; broader real-device and independent
security testing are still pending.

## Compatibility rules

- Protocol identifier: `wqrs/1`
- JSON text: UTF-8
- Canonical JSON: RFC 8785 JCS
- Binary values: unpadded URL-safe Base64
- Timestamps: non-negative Unix seconds represented as JSON integers
- Unknown fields: rejected
- Unsupported protocol versions: rejected
- Cryptography:
  - ECDH over NIST P-256
  - HKDF-SHA-256
  - AES-256-GCM with a 32-byte key, 12-byte IV, and 16-byte tag
- All random production values must come from the operating-system CSPRNG.
  Fixed values in `test-vectors/` are public test data and must never be reused
  in production.

The PWA uses the browser's built-in WebCrypto implementation. It does not ship
a JavaScript or WebAssembly cryptography implementation. Unsupported browsers
fail closed after feature detection.

The canonicalization helpers included here deliberately accept only JSON types
used by the protocol. Floating-point numbers are forbidden. Protocol property
names are ASCII, so their ordering is identical under JCS UTF-16 sorting and
ordinary code-point sorting.

## Base64URL sizes

| Value | Raw bytes | Unpadded characters |
|---|---:|---:|
| Device, pairing, pair, or message ID | 16 | 22 |
| P-256 private scalar, secret, or token | 32 | 43 |
| P-256 uncompressed public point | 65 | 87 |
| AES-GCM IV | 12 | 16 |

Decoders must reject padding, whitespace, non-URL-safe alphabet characters, and
decoded lengths different from the field definition.

## Pairing transcript

`schemas/pairing-transcript.schema.json` defines the transcript used to bind
both devices and the selected relay to the key derivation:

```text
transcript_hash = SHA256(JCS(pairing_transcript))

handshake_key = HKDF-SHA256(
    ikm=ECDH-P256(phone_private, pc_public),
    salt=pairing_secret,
    info=UTF8("wqrs/handshake/v1") || transcript_hash,
    length=32
)

root_key = HKDF-SHA256(
    ikm=ECDH-P256(phone_private, pc_public),
    salt=pairing_secret,
    info=UTF8("wqrs/root/v1") || transcript_hash,
    length=32
)
```

P-256 public keys use the 65-byte SEC1/X9.62 uncompressed-point encoding
(`0x04 || X || Y`). Receivers must validate the point through the platform
cryptography API. Private scalars must be in the curve's valid range and are
never sent.

`relay_origin` is a normalized origin: lowercase scheme and host, an explicit
non-default port when used, and no path, query, fragment, or credentials.
Production origins must use HTTPS. Plain HTTP is accepted only for the explicit
`localhost`, `127.0.0.1`, or `[::1]` development exception.

## Pairing QR URI

The PC renders this exact URI shape as a QR code:

```text
wqrs://pair?v=1&relay=<HTTPS_ORIGIN>&device=<16_BYTES>&pairing=<16_BYTES>&pairing_token=<32_BYTES>&pc_key=<65_BYTES>&secret=<32_BYTES>&expires=<UNIX_SECONDS>
```

Parameter names are case-sensitive. A parser must require each listed parameter
exactly once and reject unknown parameters, a fragment, credentials, a path
other than the `pair` authority, non-HTTPS relay origins outside the exact
loopback development exception, expired values, or incorrect decoded lengths.
Query values use UTF-8 percent encoding. The `pairing_secret` and pairing relay
token are different random values even though both are transported inside the
short-lived QR.

The deterministic URI in `test-vectors/wqrs-1.json` fixes parameter names,
ordering, percent encoding, and value encoding for cross-language tests.

## Encrypted envelopes

`schemas/encrypted-envelope.schema.json` covers four message types:

- `pair_request`
- `pair_result`
- `url_message`
- `delivered_ack`

The AEAD associated data is the RFC 8785 canonical UTF-8 JSON representation of
the complete envelope with only `ciphertext` removed. The ciphertext property
contains ciphertext followed by the 16-byte authentication tag.

Pairing envelopes expose the phone public key because the PC needs it to derive
the handshake key. The key is authenticated by the transcript hash and AEAD
associated data. It is not a secret.

Normal message keys are independent:

```text
message_key = HKDF-SHA256(
    ikm=root_key,
    salt=message_id,
    info=UTF8("wqrs/message-key/v1"),
    length=32
)

ack_key = HKDF-SHA256(
    ikm=root_key,
    salt=message_id,
    info=UTF8("wqrs/ack-key/v1"),
    length=32
)
```

The relay may route visible envelope fields but cannot alter them without
causing AEAD verification to fail.

## Payloads

- `pair-request-payload.schema.json`: phone label and platform presented for PC
  approval.
- `pair-result-payload.schema.json`: encrypted approval or rejection. A
  rejection intentionally contains no persistent token.
- `url-payload.schema.json`: one HTTP or HTTPS URL, at most 4096 UTF-8 bytes.
  Structural URL validation is required again after decryption.
- `delivered-ack-payload.schema.json`: proves only that the PC received,
  authenticated, and decrypted the message. It does not disclose whether the
  user opened or rejected the URL.

## Conformance vectors

`test-vectors/wqrs-1.json` contains:

- P-256 public keys and ECDH shared secret;
- canonical pairing transcript and transcript hash;
- handshake and root keys;
- encrypted pairing request and approval result;
- encrypted URL message;
- separately encrypted delivery ACK.

Regenerate it with:

```powershell
.\.venv\Scripts\python.exe protocol\generate_vectors.py
```

The generator requires the development dependencies. Verify the committed
vector using the independent Node.js implementation:

```powershell
node protocol\verify_vectors.mjs
```

Verify the same vector through the browser-compatible WebCrypto API:

```powershell
node protocol\verify_vectors_webcrypto.mjs
```

`webcrypto_conformance.mjs` contains no Node-specific import and is intended to
run unchanged in PWA browser tests. Passing under Node WebCrypto confirms API
semantics; real Android and iOS browser runs remain mandatory before release.

Regeneration is an explicit protocol change. A changed vector must be reviewed
together with its schemas, tests, technical design, and protocol version.

## Versioning

Any incompatible field, canonicalization, KDF, nonce, or associated-data change
requires a new protocol identifier. Existing `wqrs/1` meanings must never be
silently changed after release.
