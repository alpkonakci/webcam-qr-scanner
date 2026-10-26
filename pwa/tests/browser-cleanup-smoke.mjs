// Isolated, local-only browser check; no user profile, camera or OS clipboard.
// Usage: node tests/browser-cleanup-smoke.mjs <playwright> <chromium-exe> <origin> <fixtures>
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require(process.argv[2]);
const origin = new URL(process.argv[4]).origin;
assert.equal(new URL(origin).hostname, "127.0.0.1");
const fixtures = path.resolve(process.argv[5]);
const browser = await chromium.launch({ executablePath: process.argv[3], headless: true });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "en-US" });
const page = await context.newPage();
const errors = [];
const writes = [];
page.on("pageerror", error => errors.push(error.message));
page.on("request", request => { if (request.method() !== "GET") writes.push(request.url()); });
await context.route("**/*", route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
const heading = name => page.getByRole("heading", { name, exact: true });
const button = name => page.getByRole("button", { name, exact: true });
const select = name => page.locator('input[type="file"]').setInputFiles(path.join(fixtures, name));
const waitFor = locator => locator.waitFor({ state: "visible", timeout: 20_000 });
const address = () => page.locator(".result-address").innerText();

try {
  await page.goto(origin, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /Read from image/ }).press("Enter");
  await waitFor(heading("Read from image"));
  await select("link.png");
  await waitFor(heading("Link ready."));
  assert.equal(await address(), "https://example.com/image-test");
  console.log("PASS: direct image decoding preserves the validated URL");

  await button("Scan another QR").click();
  await waitFor(heading("Read from image"));
  await select("multiple.png");
  const feedback = page.locator('.image-feedback[role="alert"]');
  await waitFor(feedback);
  assert.match(await feedback.innerText(), /More than one/);
  assert.equal(await button("Read selected area").isEnabled(), false);
  await page.getByText("Select an area with the keyboard", { exact: true }).press("Enter");
  await page.getByRole("spinbutton", { name: "Width (%)", exact: true }).fill("49");
  await button("Read selected area").press("Enter");
  await waitFor(heading("Link ready."));
  assert.equal(await address(), "https://example.com/image-test");
  console.log("PASS: ambiguous images still require a selection; keyboard crop reads only that QR");

  await button("Scan another QR").click();
  const png = (await readFile(path.join(fixtures, "link.png"))).toString("base64");
  await page.evaluate(value => {
    const bytes = Uint8Array.from(atob(value), char => char.charCodeAt(0));
    const clipboardData = new DataTransfer();
    clipboardData.items.add(new File([bytes], "local-qr.png", { type: "image/png" }));
    document.dispatchEvent(new ClipboardEvent("paste", { clipboardData, bubbles: true, cancelable: true }));
  }, png);
  await waitFor(heading("Link ready."));
  assert.equal(await address(), "https://example.com/image-test");
  console.log("PASS: an image paste event reuses the direct read flow without OS clipboard access");

  await button("Scan another QR").click();
  // Delay a real file read, not our own decoder. The old operation must still
  // be pending at cancellation and finish only after the new result is shown.
  await page.evaluate(() => {
    const arrayBuffer = File.prototype.arrayBuffer;
    const createObjectURL = URL.createObjectURL;
    window.imageUrlCount = 0;
    URL.createObjectURL = function (blob) {
      window.imageUrlCount += 1;
      return createObjectURL.call(this, blob);
    };
    File.prototype.arrayBuffer = function () {
      if (this.name !== "link.png") return arrayBuffer.call(this);
      window.restoreFileRead = () => {
        File.prototype.arrayBuffer = arrayBuffer;
        URL.createObjectURL = createObjectURL;
      };
      return new Promise(resolve => {
        window.releaseOldRead = () => arrayBuffer.call(this).then(resolve);
      });
    };
  });
  await select("link.png");
  await page.waitForFunction(() => typeof window.releaseOldRead === "function");
  assert.equal(await page.locator('.image-reader[aria-busy="true"]').count(), 1);
  await button("Back").press("Escape");
  await waitFor(heading("Scan here. Continue on your PC."));
  await page.getByRole("button", { name: /Read from image/ }).click();
  await select("text.png");
  await waitFor(button("Copy text"));
  assert.equal(await page.locator("textarea").inputValue(), "Merhaba dünya! Çığ 😀\nİkinci satır.");
  const imageUrlsBeforeRelease = await page.evaluate(() => window.imageUrlCount);
  await page.evaluate(async () => {
    await window.releaseOldRead();
    // Let the released file's promise continuations finish before restoring
    // the URL observer; no decoder/image allocation may begin after cancel.
    await new Promise(resolve => setTimeout(resolve, 0));
    window.restoreFileRead();
    delete window.releaseOldRead;
    delete window.restoreFileRead;
  });
  await waitFor(button("Copy text"));
  assert.equal(await page.locator("textarea").inputValue(), "Merhaba dünya! Çığ 😀\nİkinci satır.");
  assert.equal(await page.evaluate(() => window.imageUrlCount), imageUrlsBeforeRelease,
    "A cancelled late file read must not allocate a new decoded image URL");
  await page.screenshot({ path: path.join(fixtures, "text-result-390.png"), fullPage: true });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  console.log("PASS: cancel/reopen does not leak a stale read into the next text result");
  assert.deepEqual(errors, []);
  assert.deepEqual(writes, []);
  assert.equal(context.pages().length, 1);
  console.log("PASS: no page errors, upload, send, navigation or extra tab");
} catch (error) {
  await page.screenshot({ path: path.join(fixtures, "failure.png"), fullPage: true });
  throw error;
} finally {
  await context.close();
  await browser.close();
}
