import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("renders the QR Scanner mobile PWA shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>QR Scanner — Phone-to-PC<\/title>/i);
  assert.match(html, /Scan here\. Continue on your PC\./);
  assert.match(html, /Camera scanner ready/);
  assert.match(html, /Scan a web link or PC pairing code/);
  assert.match(html, /Install app/);
  assert.match(html, /No location access/);
  assert.doesNotMatch(html, /Coming next/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Your site is taking shape/i);
});

test("applies privacy and embedding security headers", async () => {
  const response = await render();
  const csp = response.headers.get("content-security-policy") ?? "";

  assert.match(csp, /default-src 'self'/);
  assert.match(csp, /frame-ancestors 'none'/);
  assert.match(csp, /connect-src 'self'/);
  assert.match(csp, /worker-src 'self' blob:/);
  assert.equal(
    response.headers.get("permissions-policy"),
    "camera=(self), geolocation=(), microphone=()",
  );
  assert.equal(response.headers.get("referrer-policy"), "no-referrer");
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
});

test("ships an installable manifest without privileged capabilities", async () => {
  const manifest = JSON.parse(
    await readFile(new URL("public/manifest.webmanifest", root), "utf8"),
  );

  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.start_url, "/");
  assert.equal(manifest.icons.length, 3);
  assert.equal(manifest.permissions, undefined);
  assert.equal(manifest.shortcuts, undefined);
});

test("service worker never intercepts requests or caches user data", async () => {
  const source = await readFile(new URL("public/sw.js", root), "utf8");

  assert.doesNotMatch(source, /addEventListener\(["']fetch["']/);
  assert.doesNotMatch(source, /indexedDB|localStorage|sessionStorage/);
  assert.match(source, /tokens and keys are deliberately never cached/);
});

test("camera scanner is local, throttled and destroyed when closed", async () => {
  const [home, scanner, styles, packageJson, notices] = await Promise.all([
    readFile(new URL("app/PwaHome.tsx", root), "utf8"),
    readFile(new URL("app/QrScannerView.tsx", root), "utf8"),
    readFile(new URL("app/globals.css", root), "utf8"),
    readFile(new URL("package.json", root), "utf8").then(JSON.parse),
    readFile(new URL("THIRD_PARTY_NOTICES.md", root), "utf8"),
  ]);

  assert.equal(packageJson.dependencies["qr-scanner"], "1.4.2");
  assert.match(home, /onClick=\{startScanner\}/);
  assert.match(home, /scannerOpen &&/);
  assert.match(scanner, /maxScansPerSecond:\s*10/);
  assert.match(scanner, /document\.visibilityState === "hidden"/);
  assert.match(scanner, /scannerRef\.current\?\.destroy\(\)/);
  assert.doesNotMatch(scanner, /\bfetch\(|XMLHttpRequest|WebSocket|geolocation/);
  assert.match(styles, /\.result-secondary small\s*\{[^}]*color:\s*var\(--quiet\)/s);
  assert.match(styles, /\.http-warning\s*\{[^}]*color:\s*#ffd98a/s);
  assert.match(notices, /qr-scanner 1\.4\.2/);
});
