import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import * as policy from "../lib/image-policy.mjs";

const require = createRequire(import.meta.url);
const source = await readFile(new URL("../lib/image-qr.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const first = { data: "https://example.com/image-test", cornerPoints: [{x:1,y:1},{x:50,y:1},{x:50,y:50},{x:1,y:50}] };
function fixture(results, options = {}) {
  const engine = { terminate() { terminated++; } };
  const canvas = { width: 0, height: 0, getContext: () => context };
  const context = { fillRect() {}, drawImage() {}, beginPath() {}, moveTo() {}, lineTo() {}, closePath() {}, fill() { masked++; } };
  let terminated = 0, masked = 0, calls = 0;
  const exports = {};
  runInNewContext(compiled, { exports, DOMException, setTimeout, clearTimeout,
    document: { createElement: () => canvas },
    require: (name) => name === "./image-policy.mjs" ? policy : name === "qr-scanner" ? { default: {
      createQrEngine: async () => engine,
      scanImage: async (_canvas, scanOptions) => {
        assert.equal(scanOptions.qrEngine, engine); calls++;
        const result = results.shift(); if (result instanceof Error || typeof result === "string") throw result;
        return typeof result === "function" ? result() : result;
      },
    } } : require(name), ...options,
  });
  return { api: exports, canvas, stats: () => ({terminated, masked, calls}) };
}
const image = { naturalWidth: 1080, naturalHeight: 1920 };
const crop = { x: 0, y: 0, width: 1, height: 1 };
test("single QR is decoded locally and probed for another code", async () => {
  const f = fixture([first, "No QR code found"]);
  assert.equal(await f.api.scanQrImage(image, crop, new AbortController().signal), first.data);
  assert.deepEqual(f.stats(), {terminated:1, masked:1, calls:2});
  assert.equal(f.canvas.width, 0); assert.equal(f.canvas.height, 0);
});
test("multiple detected QR codes are rejected, including identical copies", async () => {
  for (const second of [first, {...first, data:"https://other.example"}]) {
    const f = fixture([first, second]);
    await assert.rejects(f.api.scanQrImage(image, crop, new AbortController().signal), /More than one/);
    assert.equal(f.stats().terminated, 1);
  }
});
test("no QR explains cropping and lost image detail", async () => {
  const f = fixture(["No QR code found"]);
  await assert.rejects(f.api.scanQrImage(image, crop, new AbortController().signal), /sharper screenshot.*cannot restore/);
  assert.equal(f.stats().terminated, 1);
});
test("a detector failure never delivers the first unverified result", async () => {
  const f = fixture([first, new Error("worker failed")]);
  await assert.rejects(f.api.scanQrImage(image, crop, new AbortController().signal), /Could not check/);
});
test("aborting an in-flight scan terminates the worker and clears the canvas", async () => {
  const controller = new AbortController();
  let started;
  const ready = new Promise(resolve => { started = resolve; });
  const f = fixture([() => { started(); return new Promise(() => {}); }]);
  const pending = f.api.scanQrImage(image, crop, controller.signal);
  await ready; controller.abort();
  await assert.rejects(pending, { name:"AbortError" });
  assert.ok(f.stats().terminated >= 1); assert.equal(f.canvas.width, 0);
});
test("pre-aborted scans do not create a decoder", async () => {
  const controller = new AbortController(); controller.abort();
  const f = fixture([]);
  await assert.rejects(f.api.scanQrImage(image, crop, controller.signal), { name:"AbortError" });
  assert.equal(f.stats().calls, 0);
});
test("scan deadline releases a stalled worker instead of leaving it running", async () => {
  let expire, started;
  const ready = new Promise(resolve => { started = resolve; });
  const f = fixture([() => { started(); return new Promise(() => {}); }], {
    setTimeout(callback) { expire = callback; return 1; }, clearTimeout() {},
  });
  const pending = f.api.scanQrImage(image, crop, new AbortController().signal);
  await ready; expire();
  await assert.rejects(pending, /took too long/);
  assert.equal(f.stats().terminated, 1); assert.equal(f.canvas.width, 0);
});
test("image reader is user-triggered, has no upload/camera APIs and cleans up", async () => {
  const [home, view] = await Promise.all([readFile(new URL("../app/PwaHome.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/QrImageView.tsx", import.meta.url), "utf8")]);
  assert.match(home, /onClick=\{startImage\}/);
  assert.match(home, /<QrImageView onCancel=\{closeImage\} onDecoded=\{handleDecoded\}/);
  assert.match(home, /scanSource === "image" \? startImage\(\) : startScanner\(\)/);
  assert.match(view, /event\.target\.value = ""/); // Same file can be selected twice.
  assert.match(view, /job\.current\?\.abort\(\)/);
  assert.match(view, /localImage\.current\?\.dispose\(\)/);
  assert.match(view, /controller\.signal\.aborted \|\| job\.current !== controller/);
  assert.match(view, /if \(!file\) return/);
  assert.match(view, /scanQrImage\(loaded\.image, \{ x: 0, y: 0, width: 1, height: 1 \}, controller\.signal\)/);
  assert.match(view, /if \(!controller\.signal\.aborted && job\.current === controller\) onDecoded\(value\)/);
  assert.match(view, /url && !busy &&/); // Crop is fallback, not a mandatory step.
  assert.doesNotMatch(`${view}\n${source}`, /\bfetch\(|XMLHttpRequest|WebSocket|localStorage|getUserMedia|sendUrl|window\.open/);
});
