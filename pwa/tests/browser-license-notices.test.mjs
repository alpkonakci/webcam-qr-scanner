import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { browserNotices } from "../scripts/browser-license-notices.mjs";

test("public browser notices contain the exact installed license material", async () => {
  const expected = await browserNotices();
  assert.equal(await readFile(new URL("../public/licenses/THIRD_PARTY_NOTICES.txt", import.meta.url), "utf8"), expected);
  for (const name of ["next", "react", "react-dom", "qr-scanner"]) {
    assert.ok(expected.includes(`===== ${name} `));
  }
  assert.ok(expected.includes("Next compiled /"));
  assert.ok(expected.includes("Copyright (c) 2026 alpkonakci"));
});
