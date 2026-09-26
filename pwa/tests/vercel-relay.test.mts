import assert from "node:assert/strict";
import test from "node:test";

process.env.SUPABASE_URL = "https://example.supabase.co";
process.env.SUPABASE_PUBLISHABLE_KEY = `sb_publishable_${"p".repeat(32)}`;
process.env.SUPABASE_SECRET_KEY = `sb_secret_${"s".repeat(32)}`;
process.env.RELAY_RATE_LIMIT_PEPPER = "r".repeat(32);

const { handleRelayRequest } = await import("../server/relay-handler.ts");

test("Vercel health and Realtime config expose no server secret", async () => {
  const health = await handleRelayRequest(
    new Request("https://scanner.example/healthz"),
  );
  assert.equal(health.status, 200);
  assert.deepEqual(await health.json(), {
    status: "ok",
    protocol: "wqrs/1",
    transport: "supabase-realtime",
  });

  const config = await handleRelayRequest(
    new Request("https://scanner.example/v1/realtime/config"),
  );
  assert.equal(config.status, 200);
  const body = await config.json() as Record<string, unknown>;
  assert.equal(body.url, "https://example.supabase.co");
  assert.equal(body.publishableKey, process.env.SUPABASE_PUBLISHABLE_KEY);
  assert.equal(body.fallback_poll_seconds, 5);
  assert.equal(body.connected_resync_seconds, 60);
  assert.doesNotMatch(JSON.stringify(body), /sb_secret_/);
});

test("device registration binds a Supabase user and stores only a token hash", async (context) => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init: RequestInit }> = [];
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async (input, init = {}) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.endsWith("/rest/v1/rpc/relay_consume_rate_limit")) {
      return Response.json([{ allowed: true, retry_after: 600 }]);
    }
    if (url.endsWith("/auth/v1/user")) {
      return Response.json({ id: "3f25129c-8558-4bdf-a37d-e70b650e25b1" });
    }
    if (url.endsWith("/rest/v1/relay_devices")) {
      const requestBody = JSON.parse(String(init.body)) as Record<string, unknown>;
      assert.equal(requestBody.realtime_user_id, "3f25129c-8558-4bdf-a37d-e70b650e25b1");
      assert.match(String(requestBody.receiver_token_hash), /^[0-9a-f]{64}$/);
      assert.doesNotMatch(String(init.body), /receiver_token"/);
      return Response.json([requestBody], { status: 201 });
    }
    throw new Error(`Unexpected test request: ${url}`);
  };

  const response = await handleRelayRequest(
    new Request("https://scanner.example/v1/devices", {
      method: "POST",
      headers: {
        Authorization: `Bearer header.${"a".repeat(48)}.signature`,
        "x-forwarded-for": "203.0.113.7",
      },
    }),
  );
  assert.equal(response.status, 201);
  const body = await response.json() as Record<string, unknown>;
  assert.equal(body.protocol, "wqrs/1");
  assert.match(String(body.device_id), /^[A-Za-z0-9_-]{22}$/);
  assert.match(String(body.receiver_token), /^[A-Za-z0-9_-]{43}$/);

  const databaseCall = calls.find((call) => call.url.endsWith("/rest/v1/relay_devices"));
  assert.ok(databaseCall);
  const headers = new Headers(databaseCall.init.headers);
  assert.equal(headers.get("apikey"), process.env.SUPABASE_SECRET_KEY);
  assert.equal(headers.get("authorization"), null);
});

test("a revoked sender receives pair_revoked without creating a delivery", async (context) => {
  const originalFetch = globalThis.fetch;
  let deliveryWriteAttempted = false;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });

  const pairId = base64Url(16, 51);
  const senderToken = base64Url(32, 61);
  globalThis.fetch = async (input, init = {}) => {
    const url = String(input);
    if (url.includes("/rest/v1/rpc/relay_cleanup")) {
      return Response.json(null);
    }
    if (url.includes("/rest/v1/relay_pairs?")) {
      return Response.json([
        {
          pair_id: pairId,
          device_id: base64Url(16, 71),
          sender_token_hash: "a".repeat(64),
          revoked_at: Math.floor(Date.now() / 1000),
        },
      ]);
    }
    if (url.includes("/rest/v1/relay_deliveries")) {
      deliveryWriteAttempted = true;
    }
    throw new Error(`Unexpected test request: ${url} ${init.method ?? "GET"}`);
  };

  const response = await handleRelayRequest(
    new Request(`https://scanner.example/v1/pairs/${pairId}/messages`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${senderToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    }),
  );

  assert.equal(response.status, 410);
  assert.deepEqual(await response.json(), {
    error: {
      code: "pair_revoked",
      message: "This phone no longer has access to the paired PC.",
    },
  });
  assert.equal(deliveryWriteAttempted, false);
});

test("unexpected relay failures never log raw exception data", async (context) => {
  const originalFetch = globalThis.fetch;
  const originalConsoleError = console.error;
  const logged: unknown[][] = [];
  context.after(() => {
    globalThis.fetch = originalFetch;
    console.error = originalConsoleError;
  });

  globalThis.fetch = async () => {
    throw new Error(
      "https://private.example/path Authorization: Bearer secret ciphertext",
    );
  };
  console.error = (...values: unknown[]) => {
    logged.push(values);
  };

  const response = await handleRelayRequest(
    new Request("https://scanner.example/v1/devices", { method: "POST" }),
  );

  assert.equal(response.status, 500);
  assert.deepEqual(await response.json(), {
    error: {
      code: "internal_error",
      message: "The relay could not process the request.",
    },
  });
  const output = JSON.stringify(logged);
  assert.doesNotMatch(output, /private\.example|Bearer secret|ciphertext/i);
});

test("chunked JSON requests are rejected before an oversized body is buffered", async (context) => {
  const originalFetch = globalThis.fetch;
  let insertedPairing = false;
  context.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (input) => {
    const url = String(input);
    if (url.includes("/rest/v1/rpc/relay_cleanup")) return Response.json(null);
    if (url.includes("/rest/v1/relay_devices?")) {
      return Response.json([{
        device_id: base64Url(16, 11),
        receiver_token_hash: "a".repeat(64),
        realtime_user_id: "3f25129c-8558-4bdf-a37d-e70b650e25b1",
        last_seen_at: null,
      }]);
    }
    if (url.includes("/rest/v1/relay_pairings")) insertedPairing = true;
    throw new Error(`Unexpected test request: ${url}`);
  };

  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('{"protocol":"wqrs/1","padding":"'));
      controller.enqueue(new Uint8Array(12 * 1024));
      controller.close();
    },
  });
  const response = await handleRelayRequest(
    new Request("https://scanner.example/v1/pairings", {
      method: "POST",
      headers: { Authorization: `Bearer ${base64Url(32, 21)}` },
      body,
      duplex: "half",
    } as RequestInit & { duplex: "half" }),
  );
  assert.equal(response.status, 413);
  assert.deepEqual(await response.json(), {
    error: { code: "request_too_large", message: "Relay request is too large." },
  });
  assert.equal(insertedPairing, false);
});

function base64Url(length: number, seed: number): string {
  const bytes = Uint8Array.from({ length }, (_, index) => (seed + index) % 256);
  return Buffer.from(bytes).toString("base64url");
}
