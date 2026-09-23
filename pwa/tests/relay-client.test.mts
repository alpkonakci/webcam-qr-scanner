import assert from "node:assert/strict";
import test from "node:test";

import {
  RelayClientError,
  abortableDelay,
  isPairRevokedError,
  removePairIfRevoked,
} from "../lib/relay-client.ts";

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
