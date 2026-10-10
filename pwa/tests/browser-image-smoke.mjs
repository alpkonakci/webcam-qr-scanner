// Optional local browser QA; Playwright is supplied by the workspace runtime.
// Usage: node tests/browser-image-smoke.mjs <playwright-module> <chromium-exe> <fixture-dir>
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
import { readFile } from "node:fs/promises";
const require = createRequire(import.meta.url);
const { chromium } = require(process.argv[2]);
const fixtureDir = path.resolve(process.argv[4]);
const browser = await chromium.launch({ executablePath: process.argv[3], headless: true });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true,
  userAgent: "Mozilla/5.0 (Linux; Android 14; SM-S721B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36" });
const page = await context.newPage();
const errors = [], transmissions = [];
page.on("pageerror", error => errors.push(error.message));
page.on("request", request => { if (request.method() !== "GET") transmissions.push(request.method() + " " + request.url()); });
await context.route("**/*", route => {
  const url = new URL(route.request().url());
  return url.hostname === "127.0.0.1" ? route.continue() : route.abort();
});
const button = name => page.getByRole("button", { name, exact: true });
const visible = async locator => { await locator.waitFor({ state: "visible", timeout: 20_000 }); };
const feedback = page.locator('.image-feedback[role="alert"]');
const select = async name => {
  await page.locator('input[type="file"]').setInputFiles(path.join(fixtureDir, name));
};
try {
  await page.goto("http://127.0.0.1:3107", { waitUntil: "networkidle" });
  await visible(page.getByRole("button", { name: /Read from image/ }));
  await page.screenshot({ path: path.join(fixtureDir, "home-390.png"), fullPage: true });
  await page.getByRole("button", { name: /Read from image/ }).click();
  await select("link.png");
  await visible(page.getByRole("heading", { name: "Link ready." }));
  assert.equal(await page.locator(".result-address").innerText(), "https://example.com/image-test");
  assert.equal(context.pages().length, 1);
  console.log("PASS: PNG automatically decoded without selecting an area, navigating or uploading");

  for (const name of ["link.png", "link.jpg", "link.webp"]) {
    await button("Scan another QR").click();
    await visible(page.getByRole("heading", { name: "Read from image" }));
    await select(name);
    await visible(page.getByRole("heading", { name: "Link ready." }));
    console.log("PASS: repeat/image-source preserved:", name);
  }
  await button("Scan another QR").click();
  await select("text.png");
  await visible(button("Copy text"));
  assert.equal(await page.locator("textarea").inputValue(), "Merhaba dünya! Çığ 😀\nİkinci satır.");
  assert.equal(await page.getByText("Send to PC", { exact: true }).count(), 0);
  console.log("PASS: text QR remains text-only");

  await button("Scan another QR").click();
  await select("blank.png");
  await visible(feedback);
  assert.match(await feedback.innerText(), /No QR code was found/);
  await visible(page.getByAltText("Selected image for local QR scanning"));
  assert.equal(await button("Read selected area").isEnabled(), false);
  console.log("PASS: no QR gives actionable guidance");
  await select("multiple.png");
  await visible(feedback);
  assert.match(await feedback.innerText(), /More than one/);
  await visible(page.getByAltText("Selected image for local QR scanning"));
  assert.equal(await button("Read selected area").isEnabled(), false);
  console.log("PASS: multiple QR codes blocked");

  // A pointer crop selects only the first QR from the same two-code image.
  const bounds = await page.locator(".image-crop-surface").boundingBox();
  await page.mouse.move(bounds.x + 1, bounds.y + 1); await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width * .49, bounds.y + bounds.height - 1, { steps: 8 });
  await page.mouse.up();
  await page.screenshot({ path: path.join(fixtureDir, "crop-390.png"), fullPage: true });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await button("Read selected area").click();
  await visible(page.getByRole("heading", { name: "Link ready." }));
  assert.equal(await page.locator(".result-address").innerText(), "https://example.com/image-test");
  console.log("PASS: original-pixel crop reads the chosen QR without mobile overflow");

  await button("Scan another QR").click();
  await page.locator('input[type="file"]').setInputFiles({name:"fake.png", mimeType:"image/png", buffer:Buffer.from('<svg onload="alert(1)"></svg>')});
  await visible(feedback);
  assert.match(await feedback.innerText(), /not supported/);
  console.log("PASS: forged file rejected by byte inspection");

  // Real browser clipboard APIs and an actual keyboard paste, synthetic QR only.
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {origin:"http://127.0.0.1:3107"});
  const imageBase64 = (await readFile(path.join(fixtureDir,"link.png"))).toString("base64");
  const copyImage = () => page.evaluate(async value => {
    const bytes = Uint8Array.from(atob(value), char => char.charCodeAt(0));
    await navigator.clipboard.write([new ClipboardItem({"image/png":new Blob([bytes],{type:"image/png"})})]);
  }, imageBase64);
  await copyImage();
  await page.getByRole("button", {name:/Paste image/}).click();
  await visible(page.getByRole("heading",{name:"Link ready."}));
  await page.screenshot({path:path.join(fixtureDir,"paste-390.png"),fullPage:true});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  assert.equal(await page.locator(".result-address").innerText(),"https://example.com/image-test");
  console.log("PASS: clipboard button automatically reads an actual PNG locally without mobile overflow");
  await button("Scan another QR").click();
  await copyImage();
  await button("Back").focus();
  await page.keyboard.press("Control+v");
  await visible(page.getByRole("heading",{name:"Link ready."}));
  console.log("PASS: Ctrl+V reuses the same image without another permission read");
  await button("Scan another QR").click();
  await page.evaluate(() => navigator.clipboard.writeText("https://example.com/not-an-image"));
  await page.getByRole("button",{name:/Paste image/}).click();
  await visible(feedback); assert.match(await feedback.innerText(), /image itself/);
  console.log("PASS: copied URL is not fetched or treated as an image");
  await button("Back").click();
  await visible(page.getByRole("heading", {name:"Scan here. Continue on your PC."}));
  assert.deepEqual(transmissions, []); assert.deepEqual(errors, []);
  console.log("PASS: no POST/upload, camera use or page errors; Back returns home");
} catch (error) {
  await page.screenshot({ path: path.join(fixtureDir, "failure.png"), fullPage: true });
  throw error;
} finally { await context.close(); await browser.close(); }
