import assert from "node:assert/strict";
import test from "node:test";
import { parseQrPayload } from "../lib/qr-payload.mjs";
import { parseWebUrl } from "../lib/url-policy.mjs";

test("web links retain the existing URL policy", () => {
  for (const value of ["https://example.com/", "http://example.com/a", "https://u:p@example.com", "https://"])
    assert.deepEqual(parseQrPayload(value), { kind: "link", result: parseWebUrl(value) });
});

test("short multiline text is preserved and never treated as a link", () => {
  for (const text of ["  Türkçe 😀\nİkinci satır  ", "<script>alert(1)</script>", "WIFI:T:WPA;S:example;;", "powershell Get-Item ."])
    assert.deepEqual(parseQrPayload(text), { kind: "text", text });
});

test("dangerous schemes and malformed web links remain rejected", () => {
  for (const value of ["javascript:alert(1)", "data:text/html,test", "file:///secret", "vbscript:run", "https://u:p@example.com", "https://ex\nample.com"])
    assert.equal(parseQrPayload(value).result.ok, false);
});

test("empty, oversized and control-character payloads are rejected", () => {
  for (const value of [null, {}, "  ", "a".repeat(4097), "a\0b", "a\u007fb"])
    assert.equal(parseQrPayload(value).result.ok, false);
});
