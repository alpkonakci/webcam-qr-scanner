import assert from "node:assert/strict";
import test from "node:test";
import { acknowledgeScannerReturn, parseScannerReturn } from "../lib/scanner-return.ts";

function fragment(expiresAt: number, version = 1): string {
  const bytes = Buffer.alloc(53, 12);
  bytes[0] = version;
  bytes.writeUInt32BE(expiresAt, 49);
  return `#open=${bytes.toString("base64url")}`;
}

test("scanner return accepts only a bounded canonical v1 payload", () => {
  const value = parseScannerReturn(fragment(1100), 1000);
  assert.equal(value?.expiresAt, 1100);
  assert.equal(value?.pairingId.length, 22);
  assert.equal(value?.token.length, 43);
  assert.deepEqual(Object.keys(value!), ["pairingId", "token", "expiresAt"]);
  for (const invalid of [fragment(1000), fragment(999), fragment(1121), fragment(1100, 2), "#open=bad", fragment(1100) + "&host=https://evil.example"]) {
    assert.equal(parseScannerReturn(invalid, 1000), null);
  }
});

test("scanner return uses only local opened endpoint and no pairing request", async () => {
  const value = parseScannerReturn(fragment(Math.floor(Date.now() / 1000) + 100))!;
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async (url, init) => {
    calls += 1;
    assert.equal(url, `/v1/pairings/${value.pairingId}/opened`);
    assert.equal(init?.method, "POST");
    assert.equal(init?.credentials, "same-origin");
    assert.equal(init?.referrerPolicy, "no-referrer");
    assert.equal(init?.body, undefined);
    return new Response(null, { status: calls === 1 ? 503 : 202 });
  };
  try { await acknowledgeScannerReturn(value); assert.equal(calls, 2); }
  finally { globalThis.fetch = original; }
});

test("expired or aborted return never sends a request", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error("unexpected network access"); };
  try {
    const value = { pairingId: "a".repeat(22), token: "b".repeat(43), expiresAt: 1 };
    await acknowledgeScannerReturn(value);
    const stop = new AbortController(); stop.abort();
    await acknowledgeScannerReturn({ ...value, expiresAt: Math.floor(Date.now() / 1000) + 100 }, stop.signal);
  } finally { globalThis.fetch = original; }
});
