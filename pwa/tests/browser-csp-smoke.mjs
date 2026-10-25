// Optional production-browser check. Arguments: playwright-module chromium-exe QR-image.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require(process.argv[2]);
const origin = "http://127.0.0.1:3114";
const browser = await chromium.launch({ executablePath: process.argv[3], headless: true,
  args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "en-US" });
const errors = [];
const page = await context.newPage();
page.on("pageerror", error => errors.push(error.message));
try {
  const response = await page.goto(origin, { waitUntil: "networkidle" });
  const csp = response.headers()["content-security-policy"];
  const nonce = csp.match(/'nonce-([^']+)'/)?.[1];
  assert.ok(nonce);
  assert.doesNotMatch(csp.split(";").find(item => item.trim().startsWith("script-src ")), /unsafe-inline|unsafe-eval/);
  assert.match(response.headers()["cache-control"], /no-store/);
  assert.equal(await page.evaluate(n => [...document.scripts].every(script => script.nonce === n), nonce), true);
  await page.getByRole("button", { name: "Settings and about", exact: true }).click();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  console.log("PASS: nonce-authorized hydration and settings navigation");

  const injection = await page.evaluate(async nonce => {
    const violations = [];
    const listener = event => violations.push(event.effectiveDirective);
    document.addEventListener("securitypolicyviolation", listener);
    const append = (text, value) => {
      const script = document.createElement("script");
      if (value) script.nonce = value;
      script.textContent = text;
      document.head.append(script);
      script.remove();
    };
    append("window.__cspUnauthorized = true");
    append("window.__cspWrongNonce = true", "wrong-nonce");
    append("window.__cspAuthorized = true", nonce);
    await new Promise(resolve => setTimeout(resolve, 100));
    document.removeEventListener("securitypolicyviolation", listener);
    return { blocked: !window.__cspUnauthorized && !window.__cspWrongNonce,
      allowed: window.__cspAuthorized === true, violations };
  }, nonce);
  assert.equal(injection.blocked, true);
  assert.equal(injection.allowed, true);
  assert.ok(injection.violations.filter(value => value === "script-src-elem").length >= 2);
  console.log("PASS: missing/wrong nonce blocked, matching nonce allowed");

  await page.getByRole("button", { name: /Read from image/ }).click();
  for (let attempt = 0; attempt < 2; attempt++) {
    await page.locator('input[type="file"]').setInputFiles(process.argv[4]);
    await page.getByRole("heading", { name: "Link ready.", exact: true }).waitFor();
    assert.equal(await page.locator(".result-address").innerText(), "https://example.com/image-test");
    await page.getByRole("button", { name: "Scan another QR", exact: true }).click();
  }
  console.log("PASS: image QR worker decoding and repeated scan");
  await page.goto(origin, { waitUntil: "networkidle" });
  const nextNonce = await page.evaluate(() => document.scripts[0].nonce);
  assert.notEqual(nextNonce, nonce);
  await page.getByRole("button", { name: /Scan QR/ }).click();
  await page.locator("video").waitFor();
  await page.waitForFunction(() => document.querySelector("video")?.srcObject?.getVideoTracks().some(track => track.readyState === "live"));
  await page.keyboard.press("Escape");
  await page.locator("video").waitFor({ state: "detached" });
  assert.deepEqual(errors, []);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  console.log("PASS: fresh nonce on reload, synthetic camera opens/closes, no page errors/overflow");
} finally {
  await browser.close();
}
