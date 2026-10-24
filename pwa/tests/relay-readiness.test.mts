import assert from "node:assert/strict";
import test from "node:test";

process.env.SUPABASE_URL = "https://example.supabase.co";
process.env.SUPABASE_PUBLISHABLE_KEY = `sb_publishable_${"p".repeat(32)}`;
process.env.SUPABASE_SECRET_KEY = `sb_secret_${"s".repeat(32)}`;
process.env.RELAY_RATE_LIMIT_PEPPER = "r".repeat(32);

const { handleRelayRequest } = await import("../server/relay-handler.ts");

test("liveness keeps its existing response and never triggers cleanup or a database request", async context => {
  context.mock.method(crypto, "getRandomValues", (array: Uint8Array) => array.fill(0));
  let calls = 0;
  context.mock.method(globalThis, "fetch", async () => { calls += 1; throw new Error("database offline"); });
  const response = await handleRelayRequest(new Request("https://scanner.example/healthz"));
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ok", protocol: "wqrs/1", transport: "supabase-realtime" });
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(calls, 0, "a liveness probe must not randomly run a database write");
});

test("readiness succeeds only after a read-only zero-row database query and exposes no records or secrets", async context => {
  context.mock.method(crypto, "getRandomValues", (array: Uint8Array) => array.fill(0));
  const calls: Array<{ url: URL; method: string }> = [];
  context.mock.method(globalThis, "fetch", async (input: unknown, init: RequestInit = {}) => {
    calls.push({ url: new URL(String(input)), method: init.method ?? "GET" });
    return Response.json([]);
  });
  const response = await handleRelayRequest(new Request("https://scanner.example/readyz"));
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ready", protocol: "wqrs/1", database: "ok" });
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, "GET");
  assert.equal(calls[0].url.pathname, "/rest/v1/relay_devices");
  assert.equal(calls[0].url.searchParams.get("limit"), "0");
  assert.equal(calls[0].url.searchParams.get("select"), "device_id");
});

test("a database failure produces a generic 503 readiness error without leaking upstream details", async context => {
  context.mock.method(crypto, "getRandomValues", (array: Uint8Array) => array.fill(1));
  const messages: unknown[][] = [];
  context.mock.method(console, "error", (...args: unknown[]) => messages.push(args));
  context.mock.method(globalThis, "fetch", async () => Response.json({
    code: "08006", message: "fixture secret database URL", details: "private row",
  }, { status: 503 }));
  const response = await handleRelayRequest(new Request("https://scanner.example/readyz"));
  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), { error: { code: "relay_unavailable", message: "The relay is temporarily unavailable." } });
  assert.doesNotMatch(JSON.stringify(messages), /fixture secret|private row|sb_secret_/);
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("a malformed database success cannot be reported as ready", async context => {
  context.mock.method(crypto, "getRandomValues", (array: Uint8Array) => array.fill(1));
  context.mock.method(console, "error", () => {});
  context.mock.method(globalThis, "fetch", async () => Response.json({ unexpected: true }));
  const response = await handleRelayRequest(new Request("https://scanner.example/readyz"));
  assert.equal(response.status, 503);
});

test("an upstream timeout stays a recoverable relay error rather than a pairing removal error", async context => {
  context.mock.method(crypto, "getRandomValues", (array: Uint8Array) => array.fill(1));
  context.mock.method(console, "error", () => {});
  let signal: AbortSignal | null | undefined;
  context.mock.method(globalThis, "fetch", async (_input: unknown, init: RequestInit = {}) => {
    signal = init.signal;
    throw new DOMException("fixture secret", "TimeoutError");
  });
  const response = await handleRelayRequest(new Request("https://scanner.example/readyz"));
  assert.equal(response.status, 503);
  const body = await response.json();
  assert.equal(body.error.code, "relay_unavailable");
  assert.doesNotMatch(JSON.stringify(body), /pair_revoked|realtime_auth_required|fixture secret/);
  assert.ok(signal, "readiness must also use an abortable upstream request");
});

test("the readiness route uses its shorter production deadline on a truly stalled dependency", async context => {
  context.mock.method(crypto, "getRandomValues", (array: Uint8Array) => array.fill(1));
  context.mock.method(console, "error", () => {});
  let signal: AbortSignal | null | undefined;
  context.mock.method(globalThis, "fetch", async (_input: unknown, init: RequestInit = {}) => {
    signal = init.signal;
    return new Promise<Response>(() => {});
  });
  let watchdog: ReturnType<typeof setTimeout>;
  try {
    const response = await Promise.race([
      handleRelayRequest(new Request("https://scanner.example/readyz")),
      new Promise<undefined>(resolve => { watchdog = setTimeout(() => resolve(undefined), 3_500); }),
    ]);
    assert.ok(response, "readiness must not wait for the longer normal-operation timeout");
    assert.equal(response.status, 503);
    assert.equal(signal?.aborted, true);
  } finally {
    clearTimeout(watchdog!);
  }
});
