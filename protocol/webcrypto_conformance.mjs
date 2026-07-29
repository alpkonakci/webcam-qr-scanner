/**
 * Browser-compatible WQRS/1 conformance verifier.
 *
 * This module depends only on standard Web APIs: WebCrypto, TextEncoder,
 * TextDecoder, atob, btoa, and URLSearchParams. The PWA can run the same
 * verification logic without bundling a cryptography library.
 */

function invariant(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function decodeBase64Url(value, expectedBytes, field) {
  invariant(
    /^[A-Za-z0-9_-]+$/.test(value) && !value.includes("="),
    `${field}: invalid Base64URL`,
  );
  const base64 = value.replaceAll("-", "+").replaceAll("_", "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  const decoded = Uint8Array.from(binary, (character) =>
    character.charCodeAt(0),
  );
  if (expectedBytes !== undefined) {
    invariant(decoded.length === expectedBytes, `${field}: wrong byte length`);
  }
  invariant(encodeBase64Url(decoded) === value, `${field}: non-canonical value`);
  return decoded;
}

function encodeBase64Url(value) {
  let binary = "";
  for (const byte of value) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
}

function canonicalJson(value) {
  if (
    value === null ||
    typeof value === "boolean" ||
    typeof value === "string"
  ) {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    invariant(Number.isSafeInteger(value) && value >= 0, "invalid JSON integer");
    return String(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  invariant(typeof value === "object", "unsupported canonical JSON value");
  const keys = Object.keys(value);
  for (const key of keys) {
    invariant(/^[\x00-\x7f]+$/.test(key), "non-ASCII protocol property");
  }
  return `{${keys
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
    .join(",")}}`;
}

function concatenate(...values) {
  const length = values.reduce((total, value) => total + value.length, 0);
  const result = new Uint8Array(length);
  let offset = 0;
  for (const value of values) {
    result.set(value, offset);
    offset += value.length;
  }
  return result;
}

function equalBytes(actual, expected, field) {
  invariant(actual.length === expected.length, `${field}: length mismatch`);
  let difference = 0;
  for (let index = 0; index < actual.length; index += 1) {
    difference |= actual[index] ^ expected[index];
  }
  invariant(difference === 0, `${field}: value mismatch`);
}

function p256PrivateJwk(privateKey, publicPoint) {
  invariant(publicPoint.length === 65 && publicPoint[0] === 4, "invalid P-256 point");
  return {
    kty: "EC",
    crv: "P-256",
    d: encodeBase64Url(privateKey),
    x: encodeBase64Url(publicPoint.slice(1, 33)),
    y: encodeBase64Url(publicPoint.slice(33, 65)),
    ext: true,
    key_ops: ["deriveBits"],
  };
}

async function deriveP256Secret(subtle, privateBytes, publicBytes) {
  const privateKey = await subtle.importKey(
    "jwk",
    p256PrivateJwk(privateBytes, publicBytes.own),
    { name: "ECDH", namedCurve: "P-256" },
    false,
    ["deriveBits"],
  );
  const peerPublicKey = await subtle.importKey(
    "raw",
    publicBytes.peer,
    { name: "ECDH", namedCurve: "P-256" },
    false,
    [],
  );
  return new Uint8Array(
    await subtle.deriveBits(
      { name: "ECDH", public: peerPublicKey },
      privateKey,
      256,
    ),
  );
}

async function hkdf(subtle, ikm, salt, info) {
  const keyMaterial = await subtle.importKey(
    "raw",
    ikm,
    "HKDF",
    false,
    ["deriveBits"],
  );
  return new Uint8Array(
    await subtle.deriveBits(
      {
        name: "HKDF",
        hash: "SHA-256",
        salt,
        info,
      },
      keyMaterial,
      256,
    ),
  );
}

async function decryptCase(subtle, vector, name, rawKey) {
  const testCase = vector.cases[name];
  const { ciphertext: encodedCiphertext, ...aadFields } = testCase.envelope;
  const aadText = canonicalJson(aadFields);
  invariant(aadText === testCase.aad_jcs, `${name}: AAD mismatch`);

  const key = await subtle.importKey(
    "raw",
    rawKey,
    { name: "AES-GCM", length: 256 },
    false,
    ["decrypt"],
  );
  const plaintext = await subtle.decrypt(
    {
      name: "AES-GCM",
      iv: decodeBase64Url(aadFields.nonce, 12, `${name}.nonce`),
      additionalData: new TextEncoder().encode(aadText),
      tagLength: 128,
    },
    key,
    decodeBase64Url(encodedCiphertext, undefined, `${name}.ciphertext`),
  );
  const plaintextText = new TextDecoder("utf-8", { fatal: true }).decode(
    plaintext,
  );
  invariant(plaintextText === testCase.payload_jcs, `${name}: payload mismatch`);
  invariant(
    plaintextText === canonicalJson(testCase.payload),
    `${name}: payload canonicalization mismatch`,
  );
}

export async function verifyWqrsVector(vector, cryptoApi = globalThis.crypto) {
  invariant(cryptoApi?.subtle, "WebCrypto SubtleCrypto is unavailable");
  invariant(vector.vector_version === 1, "unsupported vector version");
  invariant(vector.protocol === "wqrs/1", "unsupported protocol");

  const subtle = cryptoApi.subtle;
  const inputs = vector.inputs;
  const derived = vector.derived;
  const encoder = new TextEncoder();
  const phonePrivate = decodeBase64Url(
    inputs.phone_private_key,
    32,
    "phone_private_key",
  );
  const phonePublic = decodeBase64Url(
    derived.phone_public_key,
    65,
    "phone_public_key",
  );
  const pcPublic = decodeBase64Url(
    derived.pc_public_key,
    65,
    "pc_public_key",
  );
  const sharedSecret = await deriveP256Secret(subtle, phonePrivate, {
    own: phonePublic,
    peer: pcPublic,
  });
  equalBytes(
    sharedSecret,
    decodeBase64Url(derived.shared_secret, 32, "shared_secret"),
    "shared_secret",
  );

  const transcriptText = canonicalJson(derived.pairing_transcript);
  invariant(
    transcriptText === derived.pairing_transcript_jcs,
    "pairing transcript canonicalization mismatch",
  );
  const transcriptHash = new Uint8Array(
    await subtle.digest("SHA-256", encoder.encode(transcriptText)),
  );
  equalBytes(
    transcriptHash,
    decodeBase64Url(derived.transcript_hash, 32, "transcript_hash"),
    "transcript_hash",
  );

  const pairingSecret = decodeBase64Url(
    inputs.pairing_secret,
    32,
    "pairing_secret",
  );
  const handshakeKey = await hkdf(
    subtle,
    sharedSecret,
    pairingSecret,
    concatenate(encoder.encode("wqrs/handshake/v1"), transcriptHash),
  );
  const rootKey = await hkdf(
    subtle,
    sharedSecret,
    pairingSecret,
    concatenate(encoder.encode("wqrs/root/v1"), transcriptHash),
  );
  equalBytes(
    handshakeKey,
    decodeBase64Url(derived.handshake_key, 32, "handshake_key"),
    "handshake_key",
  );
  equalBytes(
    rootKey,
    decodeBase64Url(derived.root_key, 32, "root_key"),
    "root_key",
  );

  const pairingParameters = new URLSearchParams([
    ["v", "1"],
    ["relay", derived.pairing_transcript.relay_origin],
    ["device", inputs.device_id],
    ["pairing", inputs.pairing_id],
    ["pairing_token", inputs.pairing_relay_token],
    ["pc_key", derived.pc_public_key],
    ["secret", inputs.pairing_secret],
    ["expires", String(derived.pairing_transcript.expires_at)],
  ]);
  invariant(
    derived.pairing_uri === `wqrs://pair?${pairingParameters.toString()}`,
    "pairing URI mismatch",
  );

  await decryptCase(subtle, vector, "pair_request", handshakeKey);
  await decryptCase(subtle, vector, "pair_result", handshakeKey);

  const messageId = decodeBase64Url(inputs.message_id, 16, "message_id");
  const messageKey = await hkdf(
    subtle,
    rootKey,
    messageId,
    encoder.encode("wqrs/message-key/v1"),
  );
  const ackKey = await hkdf(
    subtle,
    rootKey,
    messageId,
    encoder.encode("wqrs/ack-key/v1"),
  );
  equalBytes(
    messageKey,
    decodeBase64Url(derived.message_key, 32, "message_key"),
    "message_key",
  );
  equalBytes(
    ackKey,
    decodeBase64Url(derived.ack_key, 32, "ack_key"),
    "ack_key",
  );
  await decryptCase(subtle, vector, "url_message", messageKey);
  await decryptCase(subtle, vector, "delivered_ack", ackKey);

  return true;
}

