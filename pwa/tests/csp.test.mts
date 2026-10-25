import assert from "node:assert/strict";
import test from "node:test";
import { NextRequest } from "next/server.js";
import { buildContentSecurityPolicy } from "../lib/content-security-policy.ts";

test("page responses replace untrusted CSP headers with a fresh non-cacheable nonce", async () => {
  const { proxy } = await import("../proxy.ts");
  const request = () => new NextRequest("https://scanner.example/", {
    headers: { "x-nonce": "attacker", "Content-Security-Policy": "script-src * 'unsafe-inline'" },
  });
  const first = proxy(request());
  const second = proxy(request());
  const csp = first.headers.get("content-security-policy")!;
  const nonce = csp.match(/'nonce-([A-Za-z0-9+/=]+)'/)?.[1];
  assert.ok(nonce && Buffer.from(nonce, "base64").length >= 16);
  assert.notEqual(csp, second.headers.get("content-security-policy"));
  assert.doesNotMatch(csp.split(";").find(value => value.trim().startsWith("script-src "))!, /unsafe-inline/);
  assert.equal(first.headers.get("x-middleware-request-x-nonce"), nonce);
  assert.equal(first.headers.get("x-middleware-request-content-security-policy"), csp);
  assert.equal(first.headers.get("cache-control"), "private, no-store");
  assert.doesNotMatch(csp, /attacker/);
});

test("production never permits eval and rejects nonce header injection", () => {
  const nonce = "AAECAwQFBgcICQoLDA0ODw==";
  assert.doesNotMatch(buildContentSecurityPolicy(false, nonce), /unsafe-eval/);
  assert.match(buildContentSecurityPolicy(true, nonce), /'unsafe-eval'/);
  for (const invalid of ["", "short", "x'; script-src *", "a".repeat(24) + "\r\n"])
    assert.throws(() => buildContentSecurityPolicy(false, invalid), /Invalid CSP nonce/);
});
