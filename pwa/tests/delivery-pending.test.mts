import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test, { type TestContext } from "node:test";
import { checkUrlDelivery, PendingDeliveryError, sendUrlToPc, watchUrlDelivery } from "../lib/relay-client.ts";
import { canonicalJson, decodeBase64Url, encodeBase64Url, type SenderCredentials } from "../lib/wqrs.ts";

const vector = JSON.parse(await readFile(new URL("../../protocol/test-vectors/wqrs-1.json", import.meta.url), "utf8"));

async function fixture(context: TestContext) {
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; });
  let now = Date.now();
  context.mock.method(Date, "now", () => now);
  const rootKey = await crypto.subtle.importKey(
    "raw", Uint8Array.from(decodeBase64Url(vector.derived.root_key, 32, "root key")).buffer,
    "HKDF", false, ["deriveKey"],
  );
  const credentials: SenderCredentials = {
    relayOrigin: "https://relay.example", pairId: vector.inputs.pair_id,
    senderToken: vector.inputs.sender_token, rootKey, pcLabel: "Test PC", keyEpoch: 1,
    pairedAt: Math.floor(now / 1000),
  };
  return {
    credentials,
    url: `https://example.com/${encodeURIComponent(context.name)}`,
    advance: (ms: number) => { now += ms; },
  };
}

async function receipt(credentials: SenderCredentials, messageId: string) {
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const now = Math.floor(Date.now() / 1000);
  const aad = {
    protocol: "wqrs/1", type: "delivered_ack", pair_id: credentials.pairId,
    key_epoch: 1, message_id: messageId, created_at: now, expires_at: now + 10,
    nonce: encodeBase64Url(nonce),
  };
  const key = await crypto.subtle.deriveKey({
    name: "HKDF", hash: "SHA-256",
    salt: Uint8Array.from(decodeBase64Url(messageId, 16, "message ID")).buffer,
    info: new TextEncoder().encode("wqrs/ack-key/v1"),
  }, credentials.rootKey, { name: "AES-GCM", length: 256 }, false, ["encrypt"]);
  const ciphertext = await crypto.subtle.encrypt({
    name: "AES-GCM", iv: nonce, tagLength: 128,
    additionalData: new TextEncoder().encode(canonicalJson(aad)),
  }, key, new TextEncoder().encode(canonicalJson({
    payload_version: 1, kind: "delivered", message_id: messageId,
  })));
  return { ...aad, ciphertext: encodeBase64Url(new Uint8Array(ciphertext)) };
}

test("timeout checks and rescans reuse one delivery, then verify a late receipt", async (context) => {
  const f = await fixture(context);
  let posts = 0;
  let gets = 0;
  let messageId = "";
  let delivered = false;
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") {
      posts += 1;
      messageId = JSON.parse(String(options.body)).message_id;
      return Response.json({ delivery_id: "test-delivery" }, { status: 202 });
    }
    gets += 1;
    if (delivered) return Response.json({ envelope: await receipt(f.credentials, messageId) });
    f.advance(16_000);
    return Response.json({ status: "pending" }, { status: 202 });
  };
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  await assert.rejects(checkUrlDelivery(f.credentials, f.url), PendingDeliveryError);
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  assert.equal(posts, 1);
  assert.equal(gets, 3);
  delivered = true;
  await checkUrlDelivery(f.credentials, f.url);
  const confirmedGets = gets;
  await sendUrlToPc(f.credentials, f.url);
  assert.equal(posts, 1);
  assert.equal(gets, confirmedGets);
});

test("a lost submission response remains uncertain and cannot create a duplicate", async (context) => {
  const f = await fixture(context);
  let requests = 0;
  globalThis.fetch = async () => { requests += 1; throw new TypeError("connection lost"); };
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  await assert.rejects(checkUrlDelivery(f.credentials, f.url), PendingDeliveryError);
  assert.equal(requests, 1);
});

test("automatic receipt watching verifies a late ACK using GETs only and caches it", async (context) => {
  const f = await fixture(context);
  let posts = 0;
  let gets = 0;
  let watching = false;
  let messageId = "";
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") {
      posts += 1;
      messageId = JSON.parse(String(options.body)).message_id;
      return Response.json({ delivery_id: "watched-delivery" }, { status: 202 });
    }
    gets += 1;
    if (watching && gets >= 3) return Response.json({ envelope: await receipt(f.credentials, messageId) });
    f.advance(watching ? 1500 : 16_000);
    return Response.json({ status: "pending" }, { status: 202 });
  };
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  watching = true;
  await watchUrlDelivery(f.credentials, f.url);
  f.advance(11_000); // Authenticated result is retained after raw ACK expires.
  const verifiedGets = gets;
  await checkUrlDelivery(f.credentials, f.url);
  assert.equal(posts, 1);
  assert.equal(gets, verifiedGets);
});

test("automatic watching stops on abort without sending again", async (context) => {
  const f = await fixture(context);
  let posts = 0;
  let gets = 0;
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") {
      posts += 1;
      return Response.json({ delivery_id: "abort-watch" }, { status: 202 });
    }
    gets += 1;
    f.advance(16_000);
    return Response.json({ status: "pending" }, { status: 202 });
  };
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  const controller = new AbortController();
  const watched = watchUrlDelivery(f.credentials, f.url, controller.signal);
  await new Promise((resolve) => setTimeout(resolve, 20));
  controller.abort();
  await assert.rejects(watched, { name: "AbortError" });
  assert.equal(posts, 1);
  assert.equal(gets, 2);
});

test("a stalled receipt GET times out without unlocking another POST", async (context) => {
  const f = await fixture(context);
  let posts = 0;
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") {
      posts += 1;
      return Response.json({ delivery_id: "stalled-receipt" }, { status: 202 });
    }
    f.advance(16_000);
    return Response.json({ status: "pending" }, { status: 202 });
  };
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  context.mock.timers.enable({ apis: ["setTimeout"] });
  let started!: () => void;
  const fetching = new Promise<void>((resolve) => { started = resolve; });
  globalThis.fetch = async (_url, options) => new Promise<Response>((_resolve, reject) => {
    options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
    started();
  });
  const checking = checkUrlDelivery(f.credentials, f.url);
  await fetching;
  context.mock.timers.tick(8_000);
  await assert.rejects(checking, PendingDeliveryError);
  context.mock.timers.reset();
  globalThis.fetch = async () => Response.json({ error: { code: "delivery_receipt_expired" } }, { status: 409 });
  await assert.rejects(sendUrlToPc(f.credentials, f.url), { code: "delivery_receipt_expired" });
  assert.equal(posts, 1);
});

test("aborting a receipt watch also aborts its outstanding GET", async (context) => {
  const f = await fixture(context);
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") return Response.json({ delivery_id: "abort-inflight" }, { status: 202 });
    f.advance(16_000);
    return Response.json({ status: "pending" }, { status: 202 });
  };
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  let started!: () => void;
  const fetching = new Promise<void>((resolve) => { started = resolve; });
  globalThis.fetch = async (_url, options) => new Promise<Response>((_resolve, reject) => {
    options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
    started();
  });
  const controller = new AbortController();
  const watching = watchUrlDelivery(f.credentials, f.url, controller.signal);
  await fetching;
  controller.abort();
  await assert.rejects(watching, { name: "AbortError" });
});

test("an expired receipt stays unconfirmed and never unlocks a duplicate send", async (context) => {
  const f = await fixture(context);
  let posts = 0;
  let receiptExpired = false;
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") {
      posts += 1;
      return Response.json({ delivery_id: "expired-receipt" }, { status: 202 });
    }
    if (receiptExpired) return Response.json({ error: { code: "delivery_receipt_expired" } }, { status: 409 });
    f.advance(16_000);
    return Response.json({ status: "pending" }, { status: 202 });
  };
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  receiptExpired = true;
  await assert.rejects(watchUrlDelivery(f.credentials, f.url), { code: "delivery_receipt_expired" });
  await assert.rejects(sendUrlToPc(f.credentials, f.url), { code: "delivery_receipt_expired" });
  assert.equal(posts, 1);
});

test("automatic watching is bounded by the original message expiry", async (context) => {
  const f = await fixture(context);
  let posts = 0;
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") {
      posts += 1;
      return Response.json({ delivery_id: "bounded-watch" }, { status: 202 });
    }
    f.advance(16_000);
    return Response.json({ status: "pending" }, { status: 202 });
  };
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  f.advance(300_000);
  await assert.rejects(watchUrlDelivery(f.credentials, f.url), { code: "delivery_expired" });
  assert.equal(posts, 1);
});

test("a receipt first checked after its ten-second validity cannot claim verified delivery", async (context) => {
  const f = await fixture(context);
  let messageId = "";
  let posts = 0;
  const state: { ack?: Record<string, unknown> } = {};
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") {
      posts += 1;
      messageId = JSON.parse(String(options.body)).message_id;
      return Response.json({ delivery_id: "late-check-delivery" }, { status: 202 });
    }
    if (state.ack) return Response.json({ envelope: state.ack });
    f.advance(16_000);
    return Response.json({ status: "pending" }, { status: 202 });
  };
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  state.ack = await receipt(f.credentials, messageId);
  f.advance(11_000);
  // Characterizes an unresolved UX limitation: never falsely report receipt.
  await assert.rejects(checkUrlDelivery(f.credentials, f.url), PendingDeliveryError);
  assert.equal(posts, 1);
});

test("a known offline rejection is retryable without losing the pairing", async (context) => {
  const f = await fixture(context);
  let offline = true;
  let posts = 0;
  let messageId = "";
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") {
      posts += 1;
      messageId = JSON.parse(String(options.body)).message_id;
      return offline
        ? Response.json({ error: { code: "receiver_offline" } }, { status: 409 })
        : Response.json({ delivery_id: "online-delivery" }, { status: 202 });
    }
    return Response.json({ envelope: await receipt(f.credentials, messageId) });
  };
  await assert.rejects(sendUrlToPc(f.credentials, f.url), { code: "receiver_offline" });
  offline = false;
  await sendUrlToPc(f.credentials, f.url);
  assert.equal(posts, 2);
});

test("simultaneous taps share their POST and authenticated receipt", async (context) => {
  const f = await fixture(context);
  let posts = 0;
  let messageId = "";
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") {
      posts += 1;
      messageId = JSON.parse(String(options.body)).message_id;
      return Response.json({ delivery_id: "shared-delivery" }, { status: 202 });
    }
    return Response.json({ envelope: await receipt(f.credentials, messageId) });
  };
  await Promise.all([sendUrlToPc(f.credentials, f.url), sendUrlToPc(f.credentials, f.url)]);
  assert.equal(posts, 1);
});

test("unverifiable or unavailable status never unlocks a duplicate submission", async (context) => {
  const f = await fixture(context);
  let posts = 0;
  let unavailable = false;
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") {
      posts += 1;
      return Response.json({ delivery_id: "unverified-delivery" }, { status: 202 });
    }
    f.advance(16_000);
    if (unavailable) throw new TypeError("connection lost");
    return Response.json({ envelope: { type: "delivered_ack", ciphertext: "invalid" } });
  };
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  unavailable = true;
  await assert.rejects(checkUrlDelivery(f.credentials, f.url), PendingDeliveryError);
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  assert.equal(posts, 1);
});

test("checking an expired or absent attempt never sends a new message", async (context) => {
  const f = await fixture(context);
  let posts = 0;
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") {
      posts += 1;
      return Response.json({ delivery_id: "expiring-delivery" }, { status: 202 });
    }
    f.advance(16_000);
    return Response.json({ status: "pending" }, { status: 202 });
  };
  await assert.rejects(checkUrlDelivery(f.credentials, f.url), { code: "delivery_expired" });
  assert.equal(posts, 0);
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  f.advance(301_000);
  await assert.rejects(checkUrlDelivery(f.credentials, f.url), { code: "delivery_expired" });
  assert.equal(posts, 1);
  // Only a separate, explicit Send action after expiry may create another attempt.
  await assert.rejects(sendUrlToPc(f.credentials, f.url), PendingDeliveryError);
  assert.equal(posts, 2);
});

test("revocation while awaiting receipt keeps the dedicated error code", async (context) => {
  const f = await fixture(context);
  let posts = 0;
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") {
      posts += 1;
      return Response.json({ delivery_id: "revoked-delivery" }, { status: 202 });
    }
    return Response.json({ error: { code: "pair_revoked" } }, { status: 410 });
  };
  await assert.rejects(sendUrlToPc(f.credentials, f.url), { code: "pair_revoked" });
  assert.equal(posts, 1);
});
