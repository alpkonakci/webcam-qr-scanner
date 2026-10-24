import assert from "node:assert/strict";
import { createServer } from "node:http";
import { once } from "node:events";
import test from "node:test";

process.env.SUPABASE_URL = "https://example.supabase.co";
process.env.SUPABASE_PUBLISHABLE_KEY = `sb_publishable_${"p".repeat(32)}`;
process.env.SUPABASE_SECRET_KEY = `sb_secret_${"s".repeat(32)}`;
process.env.RELAY_RATE_LIMIT_PEPPER = "r".repeat(32);

const { SupabaseAdmin, SupabaseAdminError } = await import("../server/supabase-admin.ts");

// A watchdog makes a missing production deadline an assertion failure, not a hung suite.
async function outcome(task: Promise<unknown>, watchdogMs = 250): Promise<unknown> {
  let timer: ReturnType<typeof setTimeout>;
  try {
    return await Promise.race([
      task.then(() => "unexpected success", error => error),
      new Promise(resolve => { timer = setTimeout(() => resolve("no deadline"), watchdogMs); }),
    ]);
  } finally {
    clearTimeout(timer!);
  }
}

for (const operation of ["auth", "select", "insert", "update", "delete", "rpc"] as const) {
  test(`${operation} aborts a stalled upstream without retrying or reporting invalid credentials`, async context => {
    let calls = 0;
    let signal: AbortSignal | null | undefined;
    context.mock.method(globalThis, "fetch", async (_input: unknown, init: RequestInit = {}) => {
      calls += 1;
      signal = init.signal;
      return new Promise<Response>(() => {});
    });
    const admin = new SupabaseAdmin(20);
    const query = new URLSearchParams({ device_id: "eq.fixture" });
    const task = operation === "auth" ? admin.authenticatedUserId("fixture-access-token")
      : operation === "select" ? admin.select("relay_devices", query)
      : operation === "insert" ? admin.insert("relay_deliveries", { fixture: true })
      : operation === "update" ? admin.update("relay_pairs", query, { fixture: true })
      : operation === "delete" ? admin.delete("relay_pairs", query)
      : admin.rpc("relay_claim_deliveries", { p_device_id: "fixture" });
    const error = await outcome(task);
    assert.ok(error instanceof SupabaseAdminError, "the upstream operation must have a finite deadline");
    assert.equal(error.status, 503);
    assert.equal(error.code, "supabase_timeout");
    assert.equal(signal?.aborted, true, "timeout must also cancel the outgoing request");
    assert.equal(calls, 1, "a timed-out write must not be blindly retried");
  });
}

for (const status of [200, 503]) {
  test(`the deadline covers a stalled ${status} response body after real HTTP headers arrive`, async context => {
    const server = createServer((_request, response) => {
      response.writeHead(status, { "Content-Type": "application/json" });
      response.write("{"); // Headers arrive, JSON body never completes.
    });
    server.listen(0, "127.0.0.1");
    await once(server, "listening");
    context.after(() => { server.closeAllConnections(); server.close(); });
    const address = server.address();
    assert.ok(address && typeof address !== "string");
    const realFetch = globalThis.fetch;
    let receivedHeaders = false;
    context.mock.method(globalThis, "fetch", async (_input: unknown, init: RequestInit = {}) => {
      const response = await realFetch(`http://127.0.0.1:${address.port}/`, init);
      receivedHeaders = true;
      return response;
    });
    const error = await outcome(new SupabaseAdmin(300).select("relay_devices", new URLSearchParams()), 2_000);
    assert.equal(receivedHeaders, true);
    assert.ok(error instanceof SupabaseAdminError, "body reading must share the upstream deadline");
    assert.equal(error.code, "supabase_timeout");
    assert.equal(error.status, 503);
  });
}

test("an unavailable auth service is recoverable, not evidence that saved credentials were revoked", async context => {
  context.mock.method(globalThis, "fetch", async () => Response.json({ message: "fixture" }, { status: 503 }));
  const error = await outcome(new SupabaseAdmin().authenticatedUserId("fixture-access-token"));
  assert.ok(error instanceof SupabaseAdminError);
  assert.equal(error.status, 503);
  assert.notEqual(error.code, "realtime_auth_required");
});

test("real invalid auth credentials still get a 401 and normal requests still parse responses", async context => {
  context.mock.method(globalThis, "fetch", async () => Response.json({ message: "invalid" }, { status: 401 }));
  await assert.rejects(new SupabaseAdmin().authenticatedUserId("invalid"), error =>
    error instanceof SupabaseAdminError && error.status === 401 && error.code === "realtime_auth_required");
  context.mock.method(globalThis, "fetch", async () => Response.json({ id: "3f25129c-8558-4bdf-a37d-e70b650e25b1" }));
  assert.equal(await new SupabaseAdmin().authenticatedUserId("valid"), "3f25129c-8558-4bdf-a37d-e70b650e25b1");
});

test("transport failures use safe recoverable errors, not raw URL or credential details", async context => {
  context.mock.method(globalThis, "fetch", async () => {
    throw new TypeError("fixture-access-token https://private.invalid/internal");
  });
  const error = await outcome(new SupabaseAdmin().select("relay_devices", new URLSearchParams()));
  assert.ok(error instanceof SupabaseAdminError);
  assert.equal(error.status, 503);
  assert.doesNotMatch(error.message, /fixture-access-token|private\.invalid/);
});

test("the production default also bounds a stalled operation without a test timeout override", async context => {
  let signal: AbortSignal | null | undefined;
  context.mock.method(globalThis, "fetch", async (_input: unknown, init: RequestInit = {}) => {
    signal = init.signal;
    return new Promise<Response>(() => {});
  });
  const error = await outcome(new SupabaseAdmin().select("relay_devices", new URLSearchParams()), 6_500);
  assert.ok(error instanceof SupabaseAdminError, "the default must remain below the client receipt request deadline");
  assert.equal(error.code, "supabase_timeout");
  assert.equal(signal?.aborted, true);
});
