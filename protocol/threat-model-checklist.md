# WQRS/1 threat-model review checklist

This checklist must be completed before the Phone-to-PC Bridge is released.
Checking an item requires an automated test, a documented manual test, or an
explicit review note linked from the release work.

## Pairing

- [ ] Pairing IDs, secrets, and relay tokens come from the OS CSPRNG.
- [ ] Pairing QR expires after two minutes and is single-use.
- [ ] The pairing secret is never sent to or logged by the relay.
- [ ] Pairing relay tokens are sent only in the Authorization header.
- [ ] Relay stores only peppered HMAC token digests.
- [ ] Relay cannot replace either P-256 public key without AEAD failure.
- [ ] Replayed pairing requests are rejected.
- [ ] A persistent sender token is created only after PC approval.
- [ ] Reject is the default action in the PC pairing dialog.

## Message confidentiality and integrity

- [ ] Only WebCrypto or reviewed platform APIs implement ECDH, HKDF, and AEAD.
- [ ] Pairing, URL, and ACK keys use distinct KDF contexts.
- [ ] Every encrypted item uses a new 12-byte nonce.
- [ ] AAD is canonical JSON of the envelope with only ciphertext removed.
- [ ] Modified routing fields, timestamps, IDs, or key epochs fail AEAD.
- [ ] Invalid Base64URL, nonce sizes, or authentication tags fail closed.
- [ ] The relay cannot decrypt a conformance-vector URL.
- [ ] Production logs never contain plaintext URLs, keys, tokens, or ciphertext.

## Replay and time handling

- [ ] A message ID is accepted at most once inside the replay window.
- [ ] Expired and excessively future-dated messages are rejected.
- [ ] Old or unknown key epochs are rejected.
- [ ] Replay state survives a desktop process restart.
- [ ] Clock-skew behavior is bounded and tested.

## URL safety and user consent

- [ ] URL length is limited to 4096 UTF-8 bytes, not characters.
- [ ] Only HTTP and HTTPS schemes are accepted.
- [ ] URLs with credentials, control characters, or invalid ports are rejected.
- [ ] The PC validates the URL again after successful decryption.
- [ ] Unicode hosts are also shown as Punycode.
- [ ] Plain HTTP produces an additional warning.
- [ ] Open is never the default action.
- [ ] Delivery ACK does not reveal whether the user opened the URL.

## Device storage and revocation

- [ ] Windows keys use current-user DPAPI, never machine-wide DPAPI.
- [ ] PWA stores the root key as a non-extractable CryptoKey in IndexedDB.
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

- [ ] Python and an independent implementation pass the committed vectors.
- [ ] Browser WebCrypto passes the same vectors before the PWA release.
- [ ] Real Android and iOS browser tests request only camera permission.
- [ ] Unsupported WebCrypto or camera capabilities fail closed with a clear
      compatibility message.
- [ ] Existing camera, screen-scan, FPS, self-test, and packaging tests pass.
- [ ] Protocol and cryptography receive an independent security review.
