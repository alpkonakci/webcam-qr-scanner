import assert from "node:assert/strict";
import test from "node:test";
import { selectHomeView, pairingGuideStatus } from "../lib/home-view.ts";

const empty = { settingsOpen: false, imageOpen: false, pairingUri: null, scanResult: null };

test("view selection keeps settings and image editing ahead of pending results", () => {
  const pending = { ...empty, pairingUri: "wqrs:test", scanResult: { kind: "text" as const, text: "saved text" } };
  assert.deepEqual(selectHomeView({ ...pending, settingsOpen: true, imageOpen: true }),
    { kind: "settings", titleId: "settings-title" });
  assert.deepEqual(selectHomeView({ ...pending, imageOpen: true }),
    { kind: "image", titleId: "image-reader-title" });
  assert.deepEqual(selectHomeView(pending),
    { kind: "pairing", titleId: "pairing-title", uri: "wqrs:test" });
});

test("result views preserve their payload and have the matching accessible heading", () => {
  assert.deepEqual(selectHomeView({ ...empty, scanResult: { kind: "text", text: "Çığ 😀\nline 2" } }),
    { kind: "text", titleId: "text-result-title", text: "Çığ 😀\nline 2" });
  const result = { ok: false as const, reason: "Unsafe URL" };
  assert.deepEqual(selectHomeView({ ...empty, scanResult: { kind: "link", result } }),
    { kind: "link", titleId: "link-result-title", result: { ok: false, reason: "Unsafe URL" } });
  assert.deepEqual(selectHomeView(empty), { kind: "home", titleId: "page-title" });
});

test("guide never mistakes an unreadable store for a missing pairing", () => {
  assert.equal(pairingGuideStatus({ ready: false, error: true, hasPair: false }), "checking");
  assert.equal(pairingGuideStatus({ ready: true, error: true, hasPair: false }), "unavailable");
  assert.equal(pairingGuideStatus({ ready: true, error: true, hasPair: true }), "unavailable");
  assert.equal(pairingGuideStatus({ ready: true, error: false, hasPair: true }), "available");
  assert.equal(pairingGuideStatus({ ready: true, error: false, hasPair: false }), "missing");
});
