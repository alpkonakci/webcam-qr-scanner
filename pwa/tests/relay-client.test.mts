import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  RelayClientError,
  abortableDelay,
  isPairRevokedError,
  removePairIfRevoked,
  sendUrlToPc,
} from "../lib/relay-client.ts";
import { decodeBase64Url, type SenderCredentials } from "../lib/wqrs.ts";

const vector = JSON.parse(
  await readFile(new URL("../../protocol/test-vectors/wqrs-1.json", import.meta.url), "utf8"),
);

test("relay fetch permits only same-origin deployment cookies", async () => {
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
  const originalFetch = globalThis.fetch;
  let fetchOptions: RequestInit | undefined;
  globalThis.fetch = async (_url, options) => {
    fetchOptions = options;
    return Response.json({ error: { code: "receiver_offline" } }, { status: 409 });
  };
  try {
    await assert.rejects(sendUrlToPc(credentials, "https://example.com"), {
      code: "receiver_offline",
    });
    assert.equal(fetchOptions?.credentials, "same-origin");
    assert.equal(fetchOptions?.referrerPolicy, "no-referrer");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("polling delay resolves normally and rejects promptly when cancelled", async () => {
  const completed = new AbortController();
  const signal = completed.signal;
  const addListener = signal.addEventListener.bind(signal);
  const removeListener = signal.removeEventListener.bind(signal);
  let activeListeners = 0;
  signal.addEventListener = ((...args: Parameters<AbortSignal["addEventListener"]>) => {
    activeListeners += 1;
    return addListener(...args);
  }) as AbortSignal["addEventListener"];
  signal.removeEventListener = ((...args: Parameters<AbortSignal["removeEventListener"]>) => {
    activeListeners -= 1;
    return removeListener(...args);
  }) as AbortSignal["removeEventListener"];
  await abortableDelay(1, signal);
  assert.equal(activeListeners, 0);

  const controller = new AbortController();
  const pending = abortableDelay(10_000, controller.signal);
  controller.abort();
  await assert.rejects(pending, { name: "AbortError" });
  await assert.rejects(
    abortableDelay(1, controller.signal),
    { name: "AbortError" },
  );
});

test("removes only a pairing explicitly revoked by the relay", async () => {
  const removed: string[] = [];
  const removeStoredPair = async (pairId: string) => {
    removed.push(pairId);
  };

  assert.equal(
    await removePairIfRevoked(
      new RelayClientError("pair_revoked", "Pair revoked"),
      "revoked-pair",
      removeStoredPair,
    ),
    true,
  );
  assert.deepEqual(removed, ["revoked-pair"]);
});

test("keeps pairing credentials for recoverable and unrelated relay failures", async () => {
  const removed: string[] = [];
  const removeStoredPair = async (pairId: string) => {
    removed.push(pairId);
  };

  for (const code of ["relay_unreachable", "receiver_offline", "rate_limited", "unauthorized"]) {
    assert.equal(
      await removePairIfRevoked(
        new RelayClientError(code, "Delivery failed"),
        "preserved-pair",
        removeStoredPair,
      ),
      false,
    );
  }

  assert.equal(await removePairIfRevoked(new Error("Server error"), "preserved-pair", removeStoredPair), false);
  assert.deepEqual(removed, []);
});

test("recognizes only the dedicated pair_revoked relay code", () => {
  assert.equal(isPairRevokedError(new RelayClientError("pair_revoked", "Pair revoked")), true);
  assert.equal(isPairRevokedError(new RelayClientError("unauthorized", "Unauthorized")), false);
  assert.equal(isPairRevokedError(new Error("Pair revoked")), false);
});
