import assert from "node:assert/strict";
import { createHash } from "node:crypto";
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

test("pair status distinguishes active, revoked and invalid sender credentials", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; });
  const pairId = base64Url(16, 81);
  const deviceId = base64Url(16, 91);
  const senderToken = base64Url(32, 101);
  const tokenHash = createHash("sha256").update(senderToken).digest("hex");
  let revokedAt: number | null = null;
  globalThis.fetch = async (input, init = {}) => {
    const url = String(input);
    if (url.includes("/rest/v1/rpc/relay_cleanup")) return Response.json(null);
    assert.equal(init.method, "GET");
    if (url.includes("/rest/v1/relay_pairs?")) {
      const hashFilter = new URL(url).searchParams.get("sender_token_hash");
      return Response.json(hashFilter === `eq.${tokenHash}` ? [{
        pair_id: pairId,
        device_id: deviceId,
        sender_token_hash: tokenHash,
        revoked_at: revokedAt,
      }] : []);
    }
    if (url.includes("/rest/v1/relay_devices?")) {
      return Response.json([{ device_id: deviceId, last_seen_at: null }]);
    }
    throw new Error(`Unexpected test request: ${url}`);
  };
  const statusRequest = (token: string) => new Request(`https://scanner.example/v1/pairs/${pairId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  const active = await handleRelayRequest(statusRequest(senderToken));
  assert.equal(active.status, 200);
  assert.deepEqual(await active.json(), { status: "active", pair_id: pairId });

  revokedAt = Math.floor(Date.now() / 1000);
  const revoked = await handleRelayRequest(statusRequest(senderToken));
  assert.equal(revoked.status, 410);
  assert.equal((await revoked.json() as { error: { code: string } }).error.code, "pair_revoked");

  const invalid = await handleRelayRequest(statusRequest(base64Url(32, 111)));
  assert.equal(invalid.status, 401);
  assert.equal((await invalid.json() as { error: { code: string } }).error.code, "unauthorized");
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

test("Vercel ACK clears URL ciphertext but preserves replay expiry after receipt expiry", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; });
  let clock = Date.now();
  context.mock.method(Date, "now", () => clock);
  const now = Math.floor(clock / 1000);
  const pairId = base64Url(16, 19), deviceId = base64Url(16, 29), deliveryId = base64Url(16, 39);
  const receiverToken = base64Url(32, 49), senderToken = base64Url(32, 59);
  const messageId = base64Url(16, 69);
  const row: Record<string, unknown> = {
    delivery_id: deliveryId, pair_id: pairId, device_id: deviceId, message_id: messageId,
    expires_at: now + 300, status: "delivering", ack_envelope: null,
    envelope: { ciphertext: "simulated-url-ciphertext", expires_at: now + 300 },
  };
  let duplicateInserts = 0;
  globalThis.fetch = async (input, init = {}) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith("/rpc/relay_cleanup")) return Response.json(null);
    if (url.pathname.endsWith("/rpc/relay_consume_rate_limit")) return Response.json([{ allowed: true, retry_after: 60 }]);
    if (url.pathname.endsWith("/relay_devices")) return Response.json([{
      device_id: deviceId, last_seen_at: now,
      receiver_token_hash: createHash("sha256").update(receiverToken).digest("hex"),
    }]);
    if (url.pathname.endsWith("/relay_pairs")) return Response.json([{
      pair_id: pairId, device_id: deviceId, revoked_at: null,
      sender_token_hash: createHash("sha256").update(senderToken).digest("hex"),
    }]);
    if (url.pathname.endsWith("/relay_deliveries")) {
      if (init.method === "PATCH") {
        const body = JSON.parse(String(init.body));
        assert.equal(Object.hasOwn(body, "expires_at"), false);
        Object.assign(row, body);
        return Response.json([row]);
      }
      if (init.method === "POST") {
        duplicateInserts += 1;
        return Response.json({ code: "23505" }, { status: 409 });
      }
      return Response.json([row]);
    }
    throw new Error(`Unexpected audit request: ${url.pathname}`);
  };
  const ack = {
    protocol: "wqrs/1", type: "delivered_ack", pair_id: pairId, key_epoch: 1,
    message_id: messageId, created_at: now, expires_at: now + 10,
    nonce: base64Url(12, 79), ciphertext: base64Url(16, 89),
  };
  const accepted = await handleRelayRequest(new Request(
    `https://scanner.example/v1/devices/${deviceId}/deliveries/${deliveryId}`, {
      method: "POST", headers: { Authorization: `Bearer ${receiverToken}` },
      body: JSON.stringify({ event: "delivery_ack", delivery_id: deliveryId, envelope: ack }),
    },
  ));
  assert.equal(accepted.status, 202);
  assert.deepEqual(row.envelope, {});
  assert.equal(row.expires_at, now + 300);
  clock += 11_000;
  const statusRequest = () => new Request(`https://scanner.example/v1/pairs/${pairId}/deliveries/${deliveryId}`, {
    headers: { Authorization: `Bearer ${senderToken}` },
  });
  const expired = await handleRelayRequest(statusRequest());
  assert.equal(expired.status, 409);
  assert.equal((await expired.json()).error.code, "delivery_receipt_expired");
  row.ack_envelope = null; // Same shape after receipt-only cleanup.
  assert.equal((await handleRelayRequest(statusRequest())).status, 409);
  const replay = await handleRelayRequest(new Request(`https://scanner.example/v1/pairs/${pairId}/messages`, {
    method: "POST", headers: { Authorization: `Bearer ${senderToken}` },
    body: JSON.stringify({ ...ack, type: "url_message", expires_at: now + 300 }),
  }));
  assert.equal(replay.status, 409);
  assert.equal((await replay.json()).error.code, "replay_rejected");
  assert.equal(duplicateInserts, 1);
});

test("offline and stale receivers reject a send without storing its envelope", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; });
  const pairId = base64Url(16, 121);
  const token = base64Url(32, 131);
  const deviceId = base64Url(16, 141);
  const hash = createHash("sha256").update(token).digest("hex");
  const now = Math.floor(Date.now() / 1000);
  let lastSeen: number | null = null;
  let deliveryWrites = 0;
  globalThis.fetch = async (input, init = {}) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith("/rpc/relay_cleanup")) return Response.json(null);
    if (url.pathname.endsWith("/rpc/relay_consume_rate_limit")) {
      return Response.json([{ allowed: true, retry_after: 60 }]);
    }
    if (url.pathname.endsWith("/relay_pairs")) {
      assert.equal(url.searchParams.get("sender_token_hash"), `eq.${hash}`);
      return Response.json([{ pair_id: pairId, device_id: deviceId,
        sender_token_hash: hash, revoked_at: null }]);
    }
    if (url.pathname.endsWith("/relay_devices")) {
      return Response.json([{ device_id: deviceId, last_seen_at: lastSeen }]);
    }
    if (url.pathname.endsWith("/relay_deliveries")) deliveryWrites += 1;
    throw new Error(`Unexpected audit request: ${url.pathname} ${init.method}`);
  };
  for (lastSeen of [null, now - 90]) {
    const response = await handleRelayRequest(new Request(
      `https://scanner.example/v1/pairs/${pairId}/messages`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` }, body: "{}",
      },
    ));
    assert.equal(response.status, 409);
    assert.equal((await response.json()).error.code, "receiver_offline");
  }
  assert.equal(deliveryWrites, 0);
});

test("invalid message metadata is rejected before a delivery write", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; });
  const pairId = base64Url(16, 151);
  const deviceId = base64Url(16, 161);
  const token = base64Url(32, 171);
  const now = Math.floor(Date.now() / 1000);
  let deliveryWrites = 0;
  globalThis.fetch = async (input) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith("/rpc/relay_cleanup")) return Response.json(null);
    if (url.pathname.endsWith("/rpc/relay_consume_rate_limit")) {
      return Response.json([{ allowed: true, retry_after: 60 }]);
    }
    if (url.pathname.endsWith("/relay_pairs")) return Response.json([{
      pair_id: pairId, device_id: deviceId, revoked_at: null,
      sender_token_hash: createHash("sha256").update(token).digest("hex"),
    }]);
    if (url.pathname.endsWith("/relay_devices")) {
      return Response.json([{ device_id: deviceId, last_seen_at: now }]);
    }
    if (url.pathname.endsWith("/relay_deliveries")) deliveryWrites += 1;
    throw new Error(`Unexpected audit request: ${url.pathname}`);
  };
  const validShape = {
    protocol: "wqrs/1", type: "url_message", pair_id: pairId, key_epoch: 1,
    message_id: base64Url(16, 181), created_at: now, expires_at: now + 300,
    nonce: base64Url(12, 191), ciphertext: base64Url(16, 201),
  };
  for (const mutation of [
    { key_epoch: 2 }, { pair_id: base64Url(16, 211) }, { nonce: "bad" },
    { expires_at: now - 1 }, { expires_at: now + 301 },
    { created_at: now + 121, expires_at: now + 200 }, { unexpected: true },
  ]) {
    const response = await handleRelayRequest(new Request(
      `https://scanner.example/v1/pairs/${pairId}/messages`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ...validShape, ...mutation }),
      },
    ));
    assert.equal(response.status, 400);
  }
  assert.equal(deliveryWrites, 0);
});

test("receiver credentials cannot claim another device's deliveries", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; });
  const actualDevice = base64Url(16, 221);
  const otherDevice = base64Url(16, 231);
  const token = base64Url(32, 241);
  const hash = createHash("sha256").update(token).digest("hex");
  let claimAttempted = false;
  globalThis.fetch = async (input) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith("/rpc/relay_cleanup")) return Response.json(null);
    if (url.pathname.endsWith("/relay_devices")) {
      assert.equal(url.searchParams.get("receiver_token_hash"), `eq.${hash}`);
      assert.equal(url.searchParams.get("device_id"), `eq.${otherDevice}`);
      return Response.json([]); // Token belongs to actualDevice, not otherDevice.
    }
    if (url.pathname.endsWith("/rpc/relay_claim_delivery")) claimAttempted = true;
    throw new Error(`Unexpected audit request: ${url.pathname}`);
  };
  assert.notEqual(actualDevice, otherDevice);
  const response = await handleRelayRequest(new Request(
    `https://scanner.example/v1/devices/${otherDevice}/messages`, {
      headers: { Authorization: `Bearer ${token}` },
    },
  ));
  assert.equal(response.status, 401);
  assert.equal(claimAttempted, false);
});

test("database replay conflict returns a safe error instead of a new delivery", async (context) => {
  const originalFetch = globalThis.fetch;
  const originalError = console.error;
  const logged: unknown[][] = [];
  context.after(() => { globalThis.fetch = originalFetch; console.error = originalError; });
  console.error = (...args) => { logged.push(args); };
  const pairId = base64Url(16, 31);
  const token = base64Url(32, 41);
  const deviceId = base64Url(16, 51);
  const now = Math.floor(Date.now() / 1000);
  globalThis.fetch = async (input) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith("/rpc/relay_cleanup")) return Response.json(null);
    if (url.pathname.endsWith("/rpc/relay_consume_rate_limit")) {
      return Response.json([{ allowed: true, retry_after: 60 }]);
    }
    if (url.pathname.endsWith("/relay_pairs")) return Response.json([{
      pair_id: pairId, device_id: deviceId, revoked_at: null,
      sender_token_hash: createHash("sha256").update(token).digest("hex"),
    }]);
    if (url.pathname.endsWith("/relay_devices")) {
      return Response.json([{ device_id: deviceId, last_seen_at: now }]);
    }
    if (url.pathname.endsWith("/relay_deliveries")) {
      return Response.json({ code: "23505", message: "private simulated database detail" }, { status: 409 });
    }
    throw new Error(`Unexpected audit request: ${url.pathname}`);
  };
  const response = await handleRelayRequest(new Request(
    `https://scanner.example/v1/pairs/${pairId}/messages`, {
      method: "POST", headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        protocol: "wqrs/1", type: "url_message", pair_id: pairId, key_epoch: 1,
        message_id: base64Url(16, 61), created_at: now, expires_at: now + 300,
        nonce: base64Url(12, 71), ciphertext: base64Url(16, 81),
      }),
    },
  ));
  assert.equal(response.status, 409);
  const body = await response.json();
  assert.equal(body.error.code, "replay_rejected");
  assert.doesNotMatch(JSON.stringify([body, logged]), /private simulated database detail/);
});
