import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { Miniflare } from "miniflare";
import { handleRelayRequest } from "../worker/relay-api.ts";

const PROTOCOL = "wqrs/1";

test("D1 relay routes only opaque envelopes and returns an authenticated receipt", async (context) => {
  const miniflare = new Miniflare({
    modules: true,
    script: "export default { fetch() { return new Response('unused') } }",
    d1Databases: ["DB"],
  });
  context.after(() => miniflare.dispose());
  const database = await miniflare.getD1Database("DB");
  const migration = await readFile(
    new URL("../drizzle/0000_lazy_blade.sql", import.meta.url),
    "utf8",
  );
  for (const statement of migration.split("--> statement-breakpoint")) {
    if (statement.trim()) await database.prepare(statement.trim()).run();
  }

  const pending: Promise<unknown>[] = [];
  const request = async (
    path: string,
    init: RequestInit = {},
  ): Promise<{ response: Response; body: Record<string, unknown> }> => {
    const response = await handleRelayRequest(
      new Request(`https://relay.example${path}`, init),
      { DB: database },
      { waitUntil: (promise) => pending.push(promise) },
    );
    assert.ok(response);
    const body = response.status === 204 ? {} : await response.json() as Record<string, unknown>;
    return { response, body };
  };

  const created = await request("/v1/devices", { method: "POST" });
  assert.equal(created.response.status, 201);
  const deviceId = created.body.device_id as string;
  const receiverToken = created.body.receiver_token as string;
  const receiverHeaders = { Authorization: `Bearer ${receiverToken}` };

  const pairing = await request("/v1/pairings", {
    method: "POST",
    headers: { ...receiverHeaders, "Content-Type": "application/json" },
    body: JSON.stringify({ protocol: PROTOCOL }),
  });
  assert.equal(pairing.response.status, 201);
  const pairingId = pairing.body.pairing_id as string;
  const pairingToken = pairing.body.pairing_token as string;
  const expiresAt = pairing.body.expires_at as number;
  const phonePublicKey = base64Url(65, 4);
  const pairingRequest = {
    protocol: PROTOCOL,
    device_id: deviceId,
    pairing_id: pairingId,
    phone_public_key: phonePublicKey,
    expires_at: expiresAt,
    type: "pair_request",
    created_at: expiresAt - 60,
    nonce: base64Url(12, 8),
    ciphertext: base64Url(32, 12),
  };
  const submittedPairing = await request(`/v1/pairings/${pairingId}/request`, {
    method: "POST",
    headers: { Authorization: `Bearer ${pairingToken}`, "Content-Type": "application/json" },
    body: JSON.stringify(pairingRequest),
  });
  assert.equal(submittedPairing.response.status, 202);

  const receivedPairing = await request(`/v1/pairings/${pairingId}/request`, {
    headers: receiverHeaders,
  });
  assert.equal(receivedPairing.response.status, 200);
  assert.deepEqual(receivedPairing.body.envelope, pairingRequest);

  const pairId = base64Url(16, 21);
  const senderToken = base64Url(32, 23);
  const registered = await request("/v1/pairs", {
    method: "POST",
    headers: { ...receiverHeaders, "Content-Type": "application/json" },
    body: JSON.stringify({ protocol: PROTOCOL, pair_id: pairId, sender_token: senderToken }),
  });
  assert.equal(registered.response.status, 201);

  const heartbeat = await request(`/v1/devices/${deviceId}/messages`, {
    headers: receiverHeaders,
  });
  assert.equal(heartbeat.response.status, 204);

  const now = Math.floor(Date.now() / 1000);
  const messageId = base64Url(16, 29);
  const encryptedMessage = {
    protocol: PROTOCOL,
    type: "url_message",
    pair_id: pairId,
    key_epoch: 1,
    message_id: messageId,
    created_at: now,
    expires_at: now + 300,
    nonce: base64Url(12, 31),
    ciphertext: base64Url(48, 37),
  };
  const sent = await request(`/v1/pairs/${pairId}/messages`, {
    method: "POST",
    headers: { Authorization: `Bearer ${senderToken}`, "Content-Type": "application/json" },
    body: JSON.stringify(encryptedMessage),
  });
  assert.equal(sent.response.status, 202);
  const deliveryId = sent.body.delivery_id as string;

  const delivery = await request(`/v1/devices/${deviceId}/messages`, {
    headers: receiverHeaders,
  });
  assert.equal(delivery.response.status, 200);
  assert.deepEqual(delivery.body.envelope, encryptedMessage);

  const acknowledgement = {
    protocol: PROTOCOL,
    type: "delivered_ack",
    pair_id: pairId,
    key_epoch: 1,
    message_id: messageId,
    created_at: now,
    expires_at: now + 10,
    nonce: base64Url(12, 41),
    ciphertext: base64Url(32, 43),
  };
  const acknowledged = await request(
    `/v1/devices/${deviceId}/deliveries/${deliveryId}`,
    {
      method: "POST",
      headers: { ...receiverHeaders, "Content-Type": "application/json" },
      body: JSON.stringify({
        event: "delivery_ack",
        delivery_id: deliveryId,
        envelope: acknowledgement,
      }),
    },
  );
  assert.equal(acknowledged.response.status, 202);

  const status = await request(`/v1/pairs/${pairId}/deliveries/${deliveryId}`, {
    headers: { Authorization: `Bearer ${senderToken}` },
  });
  assert.equal(status.response.status, 200);
  assert.deepEqual(status.body.envelope, acknowledgement);

  const stored = await database
    .prepare("SELECT envelope FROM relay_deliveries WHERE delivery_id = ?")
    .bind(deliveryId)
    .first<{ envelope: string }>();
  assert.ok(stored);
  assert.doesNotMatch(stored.envelope, /https?:\/\//i);
  await Promise.all(pending);
});

function base64Url(length: number, seed: number): string {
  const bytes = Uint8Array.from({ length }, (_, index) => (seed + index) % 256);
  return Buffer.from(bytes).toString("base64url");
}
