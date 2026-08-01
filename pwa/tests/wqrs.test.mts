import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  canonicalJson,
  createPhonePairingAttempt,
  decodeBase64Url,
  encodeBase64Url,
  pairingUriFromLaunchFragment,
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

test("HTTPS launch fragments expose only the embedded WQRS value", () => {
  assert.equal(
    pairingUriFromLaunchFragment(
      `#${vector.derived.pairing_uri}`,
      "https://relay.example",
    ),
    vector.derived.pairing_uri,
  );
  const rawPublicKey = decodeBase64Url(
    vector.derived.pairing_transcript.pc_public_key,
    65,
    "PC public key",
  );
  const compressedPublicKey = new Uint8Array(33);
  compressedPublicKey[0] = 2 | (rawPublicKey[64] & 1);
  compressedPublicKey.set(rawPublicKey.slice(1, 33), 1);
  const compactBytes = new Uint8Array(138);
  compactBytes[0] = 1;
  compactBytes.set(decodeBase64Url(vector.inputs.device_id, 16, "device"), 1);
  compactBytes.set(decodeBase64Url(vector.inputs.pairing_id, 16, "pairing"), 17);
  compactBytes.set(
    decodeBase64Url(vector.inputs.pairing_relay_token, 32, "pairing token"),
    33,
  );
  compactBytes.set(compressedPublicKey, 65);
  compactBytes.set(
    decodeBase64Url(vector.inputs.pairing_secret, 32, "pairing secret"),
    98,
  );
  new DataView(compactBytes.buffer).setBigUint64(
    130,
    BigInt(vector.derived.pairing_transcript.expires_at),
    false,
  );
  const compact = `#p1.${encodeBase64Url(compactBytes)}`;
  assert.deepEqual(
    parsePairingUri(
      pairingUriFromLaunchFragment(compact, "https://relay.example")!,
      vector.derived.pairing_transcript.expires_at - 60,
    ),
    parsePairingUri(
      vector.derived.pairing_uri,
      vector.derived.pairing_transcript.expires_at - 60,
    ),
  );
  assert.equal(
    pairingUriFromLaunchFragment("#not-a-pairing", "https://relay.example"),
    null,
  );
  assert.equal(
    pairingUriFromLaunchFragment(
      vector.derived.pairing_uri,
      "https://relay.example",
    ),
    null,
  );
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
