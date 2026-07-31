import assert from "node:assert/strict";
import test from "node:test";

import { MAX_QR_TEXT_LENGTH, parseWebUrl } from "../lib/url-policy.mjs";

test("accepts and normalizes explicit HTTPS and HTTP links", () => {
  assert.deepEqual(parseWebUrl("  https://example.com/path?q=1  "), {
    ok: true,
    href: "https://example.com/path?q=1",
    hostname: "example.com",
    insecure: false,
  });
  assert.deepEqual(parseWebUrl("http://example.com"), {
    ok: true,
    href: "http://example.com/",
    hostname: "example.com",
    insecure: true,
  });
});

test("rejects executable and non-web URL schemes", () => {
  for (const value of [
    "javascript:alert(1)",
    "file:///C:/secret.txt",
    "data:text/html,test",
    "ftp://example.com/file",
  ]) {
    assert.equal(parseWebUrl(value).ok, false);
  }
});

test("rejects malformed, credential-bearing and hostile text", () => {
  for (const value of [
    "not a url",
    "https://user:password@example.com/",
    "https://example.com/\nnext",
    "",
    "x".repeat(MAX_QR_TEXT_LENGTH + 1),
  ]) {
    assert.equal(parseWebUrl(value).ok, false);
  }
});
