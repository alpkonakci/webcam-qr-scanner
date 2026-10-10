/**
 * Independent Node.js verifier for the committed WQRS/1 Python vectors.
 *
 * This file uses only Node's built-in crypto APIs. It intentionally does not
 * share implementation code with generate_vectors.py.
 */

import assert from "node:assert/strict";
import {
  createDecipheriv,
  createECDH,
  createHash,
  hkdfSync,
} from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const vectorPath = join(here, "test-vectors", "wqrs-1.json");
const vector = JSON.parse(readFileSync(vectorPath, "utf8"));

function decodeBase64Url(value, expectedBytes, field) {
  assert.match(value, /^[A-Za-z0-9_-]+$/, `${field}: invalid Base64URL`);
  assert.equal(value.includes("="), false, `${field}: padding is forbidden`);
  const decoded = Buffer.from(value, "base64url");
  assert.equal(
    decoded.toString("base64url"),
    value,
    `${field}: non-canonical Base64URL`,
  );
  if (expectedBytes !== undefined) {
    assert.equal(decoded.length, expectedBytes, `${field}: wrong byte length`);
  }
  return decoded;
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
    assert.equal(Number.isSafeInteger(value), true, "non-safe JSON integer");
    assert.ok(value >= 0, "negative protocol integer");
    return String(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  assert.equal(typeof value, "object", "unsupported canonical JSON value");
  const keys = Object.keys(value);
  for (const key of keys) {
    assert.match(key, /^[\x00-\x7f]+$/, "non-ASCII protocol property name");
  }
  return `{${keys
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
    .join(",")}}`;
}

function p256KeyPair(rawPrivateKey) {
  assert.equal(rawPrivateKey.length, 32);
  const keyPair = createECDH("prime256v1");
  keyPair.setPrivateKey(rawPrivateKey);
  return keyPair;
}

function hkdf(ikm, salt, info) {
  return Buffer.from(hkdfSync("sha256", ikm, salt, info, 32));
}

function assertBytes(actual, expectedEncoded, field) {
  const expected = decodeBase64Url(expectedEncoded, actual.length, field);
  assert.equal(Buffer.compare(actual, expected), 0, `${field}: value mismatch`);
}

function decryptCase(name, key) {
  const testCase = vector.cases[name];
  const { ciphertext: encodedCiphertext, ...aadFields } = testCase.envelope;
  const aad = Buffer.from(canonicalJson(aadFields), "utf8");
  assert.equal(aad.toString("utf8"), testCase.aad_jcs, `${name}: AAD mismatch`);

  const nonce = decodeBase64Url(aadFields.nonce, 12, `${name}.nonce`);
  const combined = decodeBase64Url(
    encodedCiphertext,
    undefined,
    `${name}.ciphertext`,
  );
  assert.ok(combined.length >= 16, `${name}: missing authentication tag`);
  const encrypted = combined.subarray(0, -16);
  const tag = combined.subarray(-16);

  const decipher = createDecipheriv("aes-256-gcm", key, nonce, {
    authTagLength: 16,
  });
  decipher.setAAD(aad);
  decipher.setAuthTag(tag);
  const plaintext = Buffer.concat([
    decipher.update(encrypted),
    decipher.final(),
  ]);

  assert.equal(
    plaintext.toString("utf8"),
    testCase.payload_jcs,
    `${name}: plaintext mismatch`,
  );
  assert.equal(
    plaintext.toString("utf8"),
    canonicalJson(testCase.payload),
    `${name}: payload canonicalization mismatch`,
  );

  const damaged = Buffer.from(encrypted);
  damaged[0] ^= 1;
  assert.throws(() => {
    const tampered = createDecipheriv("aes-256-gcm", key, nonce, {
      authTagLength: 16,
    });
    tampered.setAAD(aad);
    tampered.setAuthTag(tag);
    tampered.update(damaged);
    tampered.final();
  }, `${name}: tampered ciphertext was accepted`);
}

assert.equal(vector.vector_version, 1);
assert.equal(vector.protocol, "wqrs/1");

const inputs = vector.inputs;
const derived = vector.derived;
const pcKeyPair = p256KeyPair(
  decodeBase64Url(inputs.pc_private_key, 32, "pc_private_key"),
);
const phoneKeyPair = p256KeyPair(
  decodeBase64Url(inputs.phone_private_key, 32, "phone_private_key"),
);
const pcPublicRaw = pcKeyPair.getPublicKey(undefined, "uncompressed");
const phonePublicRaw = phoneKeyPair.getPublicKey(undefined, "uncompressed");
assertBytes(pcPublicRaw, derived.pc_public_key, "pc_public_key");
assertBytes(phonePublicRaw, derived.phone_public_key, "phone_public_key");

const sharedSecret = phoneKeyPair.computeSecret(pcPublicRaw);
assertBytes(sharedSecret, derived.shared_secret, "shared_secret");

const transcriptJcs = Buffer.from(
  canonicalJson(derived.pairing_transcript),
  "utf8",
);
assert.equal(
  transcriptJcs.toString("utf8"),
  derived.pairing_transcript_jcs,
  "pairing transcript canonicalization mismatch",
);
const transcriptHash = createHash("sha256").update(transcriptJcs).digest();
assertBytes(transcriptHash, derived.transcript_hash, "transcript_hash");

const pairingSecret = decodeBase64Url(
  inputs.pairing_secret,
  32,
  "pairing_secret",
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
assert.equal(
  derived.pairing_uri,
  `wqrs://pair?${pairingParameters.toString()}`,
  "pairing URI mismatch",
);
const handshakeKey = hkdf(
  sharedSecret,
  pairingSecret,
  Buffer.concat([Buffer.from("wqrs/handshake/v1"), transcriptHash]),
);
const rootKey = hkdf(
  sharedSecret,
  pairingSecret,
  Buffer.concat([Buffer.from("wqrs/root/v1"), transcriptHash]),
);
assertBytes(handshakeKey, derived.handshake_key, "handshake_key");
assertBytes(rootKey, derived.root_key, "root_key");

decryptCase("pair_request", handshakeKey);
decryptCase("pair_result", handshakeKey);

const messageId = decodeBase64Url(inputs.message_id, 16, "message_id");
const messageKey = hkdf(
  rootKey,
  messageId,
  Buffer.from("wqrs/message-key/v1"),
);
const ackKey = hkdf(rootKey, messageId, Buffer.from("wqrs/ack-key/v1"));
assertBytes(messageKey, derived.message_key, "message_key");
assertBytes(ackKey, derived.ack_key, "ack_key");
assert.notEqual(
  messageKey.toString("hex"),
  ackKey.toString("hex"),
  "message and ACK keys must differ",
);

decryptCase("url_message", messageKey);
decryptCase("delivered_ack", ackKey);

console.log("WQRS/1 vectors verified independently with Node.js.");
