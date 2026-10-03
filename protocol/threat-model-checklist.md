# WQRS/1 threat-model review checklist

This checklist must be completed before the Phone-to-PC Bridge is released.
Checking an item requires an automated test, a documented manual test, or an
explicit review note linked from the release work.

2026-10-03 internal audit evidence is recorded in
[the main readiness report](../docs/main-readiness-audit-2026-10-03.md).
Checked items below mean source/test evidence, not independent certification.
The [2026-10-04 local fix follow-up](../docs/main-readiness-fixes-2026-10-04.md)
records a passing restart probe and separate-process Windows DPAPI test.
The [beta.3 publication record](../docs/v0.2.0-beta.3-verification-2026-10-04.md)
records the applied migration and matching production deployment. Plain SHA-256
token hashing, Postgres envelope retention and inline-script CSP exceptions
still do not meet their original requirement wording; those items remain open.

## Pairing

- [x] Pairing IDs, secrets, and relay tokens come from the OS CSPRNG.
- [ ] Pairing QR expires after two minutes and is single-use.
- [ ] The pairing secret is never sent to or logged by the relay.
- [x] HTTPS launch links keep pairing material in the URL fragment, and the PWA
  clears that fragment immediately after local consumption.
- [x] Pairing relay tokens are sent only in the Authorization header.
- [ ] Browser-open and phone-cancel lifecycle signals require the short-lived
  pairing bearer token and never grant pairing approval.
- [ ] Relay stores only peppered HMAC token digests.
- [ ] Relay cannot replace either P-256 public key without AEAD failure.
- [ ] Replayed pairing requests are rejected.
- [ ] A persistent sender token is created only after proof of the short-lived,
  single-use QR secret and a valid authenticated pairing request.
- [x] Scanning and submitting the desktop QR is documented as the explicit
  pairing authorization; no redundant second desktop prompt is shown.

## Message confidentiality and integrity

- [x] Only WebCrypto or reviewed platform APIs implement ECDH, HKDF, and AEAD.
- [x] Pairing, URL, and ACK keys use distinct KDF contexts.
- [x] Every encrypted item uses a new 12-byte nonce.
- [x] AAD is canonical JSON of the envelope with only ciphertext removed.
- [x] Modified routing fields, timestamps, IDs, or key epochs fail AEAD.
- [x] Invalid Base64URL, nonce sizes, or authentication tags fail closed.
- [ ] The relay cannot decrypt a conformance-vector URL.
- [ ] Production logs never contain plaintext URLs, keys, tokens, or ciphertext.

## Replay and time handling

- [ ] A message ID is accepted at most once inside the replay window.
- [x] Expired and excessively future-dated messages are rejected.
- [x] Old or unknown key epochs are rejected.
- [x] Replay state survives a desktop process restart (local Windows DPAPI test;
  published beta.2 is unchanged).
- [x] Clock-skew behavior is bounded and tested.

## URL safety and user consent

- [x] URL length is limited to 4096 UTF-8 bytes, not characters.
- [x] Only HTTP and HTTPS schemes are accepted.
- [x] URLs with credentials, control characters, or invalid ports are rejected.
- [x] The PC validates the URL again after successful decryption.
- [x] Unicode hosts are also shown as Punycode.
- [x] Plain HTTP produces an additional warning.
- [x] Open is never the default action.
- [x] Delivery ACK does not reveal whether the user opened the URL.

## Device storage and revocation

- [x] Windows keys use current-user DPAPI, never machine-wide DPAPI.
- [x] PWA stores the root key as a non-extractable CryptoKey in IndexedDB.
- [ ] Clearing browser site data removes the pairing and requires re-pairing.
- [ ] The PWA origin uses a strict CSP and loads no third-party scripts.
- [ ] The PWA never stores scanned or sent URL history.
- [ ] Revocation deletes local keys and invalidates the relay token digest.
- [ ] Uninstall, reinstall, and lost-device behavior is documented and tested.

## Relay and network

- [ ] Desktop creates only an outbound authenticated WSS connection.
- [ ] HTTPS/WSS requires TLS 1.2 or newer; TLS 1.3 is preferred.
- [ ] Request bodies, JSON depth, connection counts, and rates are bounded.
- [ ] Authorization headers are removed from access and exception logs.
- [ ] Pairing results and message ACKs are memory-only and time-bounded.
- [ ] v0.2.0 does not persist an offline message queue on the relay.
- [ ] Relay privacy text discloses IP, timing, size, and routing metadata.

## Platform and release

- [x] Python and an independent implementation pass the committed vectors.
- [x] Browser WebCrypto passes the same vectors before the PWA release.
- [ ] Real Android and iOS browser tests request only camera permission.
- [ ] Unsupported WebCrypto or camera capabilities fail closed with a clear
      compatibility message.
- [x] Existing camera, screen-scan, FPS, self-test, and packaging tests pass.
- [ ] Protocol and cryptography receive an independent security review.
