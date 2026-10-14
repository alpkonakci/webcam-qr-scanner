import assert from "node:assert/strict";
import test from "node:test";
import { translate, chooseLanguage } from "../lib/i18n-core.ts";
import { getPcConnection } from "../lib/relay-client.ts";
import { freshConnection } from "../lib/connection-state.ts";
import type { SenderCredentials } from "../lib/wqrs.ts";

test("language selection persists valid choice and respects Turkish browser default", () => {
  assert.equal(chooseLanguage(null, "tr-TR"), "tr");
  assert.equal(chooseLanguage("en", "tr-TR"), "en");
  assert.equal(chooseLanguage("garbage", "fr-FR"), "en");
  assert.equal(translate("Replace pairing", "tr"), "Mevcut eşleşmeyi değiştir");
  assert.equal(translate("Remove", "en"), "Remove access");
  assert.equal(translate("Replace pairing", "en"), "Connect to this PC instead");
  assert.equal(translate("My PC received and verified the link.", "tr"), "My PC bağlantıyı aldı ve doğruladı.");
});

test("a saved pairing is not online evidence and a reachable lease expires", () => {
  assert.equal(freshConnection(null, 100, 0), "unknown");
  const value = { pairStatus: "active", state: "reachable", validForSeconds: 10 } as const;
  assert.equal(freshConnection(value, 10_000, 9_999), "reachable");
  assert.equal(freshConnection(value, 10_000, 10_000), "unknown");
});

test("status checks are authenticated GET only, do not send and preserve offline pairings", async (context) => {
  const original = globalThis.fetch;
  context.after(() => { globalThis.fetch = original; });
  const pair = { relayOrigin: "https://relay.example", pairId: "p".repeat(22), senderToken: "t".repeat(43) } as SenderCredentials;
  let body: Record<string, unknown> = { status: "active", pair_id: pair.pairId, reachable: true, valid_for_seconds: 12, checked_at: 100 };
  const removed: string[] = [];
  globalThis.fetch = async (url, options) => {
    assert.equal(String(url), `${pair.relayOrigin}/v1/pairs/${pair.pairId}`);
    assert.equal(options?.method, "GET");
    assert.equal(options?.body, undefined);
    assert.equal(new Headers(options?.headers).get("Authorization"), `Bearer ${pair.senderToken}`);
    return Response.json(body);
  };
  const options = { removeStoredPair: async (id: string) => { removed.push(id); } };
  assert.equal((await getPcConnection(pair, options)).state, "reachable");
  body = { ...body, reachable: false, valid_for_seconds: 0 };
  assert.equal((await getPcConnection(pair, options)).state, "unreachable");
  body = { status: "active", pair_id: pair.pairId };
  assert.equal((await getPcConnection(pair, options)).state, "unknown");
  body = { ...body, reachable: true, valid_for_seconds: 9999, checked_at: 100 };
  assert.equal((await getPcConnection(pair, options)).state, "unknown");
  assert.deepEqual(removed, []);
});
