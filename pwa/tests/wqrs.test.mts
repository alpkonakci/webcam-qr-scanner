import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  canonicalJson,
  createPhonePairingAttempt,
  decodeBase64Url,
  parsePairingUri,
  verifyDeliveryAck,
  type SenderCredentials,
} from "../lib/wqrs.ts";
import { verifyWqrsVector } from "../../protocol/webcrypto_conformance.mjs";

const vector = JSON.parse(
  await readFile(new URL("../../protocol/test-vectors/wqrs-1.json", import.meta.url), "utf8"),
);

test("browser WebCrypto remains compatible with the committed WQRS/1 vector", async () => {
  assert.equal(await verifyWqrsVector(vector), true);
});

test("production pairing parser and crypto accept the committed contract", async () => {
  const expiresAt = vector.derived.pairing_transcript.expires_at;
  const qr = parsePairingUri(vector.derived.pairing_uri, expiresAt - 60);

  assert.equal(qr.pairingId, vector.inputs.pairing_id);
  assert.equal(qr.relayOrigin, "https://relay.example");
  const attempt = await createPhonePairingAttempt(
    vector.derived.pairing_uri,
    "Test phone",
    expiresAt - 60,
  );
  assert.equal(attempt.requestEnvelope.type, "pair_request");
  assert.equal(attempt.rootKey.extractable, false);
  assert.deepEqual(attempt.rootKey.usages, ["deriveKey"]);
});

test("production acknowledgement verifier authenticates the vector", async () => {
  const rootKey = await crypto.subtle.importKey(
    "raw",
    Uint8Array.from(decodeBase64Url(vector.derived.root_key, 32, "root key")).buffer,
    "HKDF",
    false,
    ["deriveKey"],
  );
  const credentials: SenderCredentials = {
    relayOrigin: "https://relay.example",
    pairId: vector.inputs.pair_id,
    senderToken: vector.inputs.sender_token,
    rootKey,
    pcLabel: "Test PC",
    keyEpoch: 1,
    pairedAt: vector.cases.delivered_ack.envelope.created_at,
  };

  await verifyDeliveryAck(
    credentials,
    vector.inputs.message_id,
    vector.cases.delivered_ack.envelope,
    vector.cases.delivered_ack.envelope.created_at,
  );
});

test("canonical JSON rejects floating-point protocol values", () => {
  assert.throws(() => canonicalJson({ invalid: 1.5 }), /integer/i);
});
