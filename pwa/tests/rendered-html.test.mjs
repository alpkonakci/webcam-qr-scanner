import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("keeps the QR Scanner mobile PWA shell in the Vercel build", async () => {
  const [layout, home] = await Promise.all([
    readFile(new URL("app/layout.tsx", root), "utf8"),
    readFile(new URL("app/PwaHome.tsx", root), "utf8"),
  ]);
  assert.match(layout, /QR Scanner/);
  assert.match(home, /Scan here\. Continue on your PC\./);
  assert.match(home, /Camera scanner ready/);
  assert.match(home, /Scan a web link or PC pairing code/);
  assert.doesNotMatch(home, /Install app|Added to Home Screen/);
  assert.match(home, /No location access/);
  assert.doesNotMatch(`${layout}\n${home}`, /Coming next/);
  assert.doesNotMatch(
    `${layout}\n${home}`,
    /codex-preview|react-loading-skeleton|Your site is taking shape/i,
  );
});

test("applies privacy and embedding security headers", async () => {
  const {
    buildContentSecurityPolicy,
    default: nextConfig,
  } = await import("../next.config.ts");
  const entries = await nextConfig.headers();
  const headers = new Map(
    entries[0].headers.map(({ key, value }) => [key.toLowerCase(), value]),
  );
  const csp = headers.get("content-security-policy") ?? "";

  assert.match(csp, /default-src 'self'/);
  assert.match(csp, /frame-ancestors 'none'/);
  assert.match(csp, /connect-src 'self'/);
  assert.match(csp, /worker-src 'self' blob:/);
  assert.doesNotMatch(buildContentSecurityPolicy(false), /'unsafe-eval'/);
  assert.match(buildContentSecurityPolicy(true), /'unsafe-eval'/);
  assert.equal(
    headers.get("permissions-policy"),
    "camera=(self), geolocation=(), microphone=()",
  );
  assert.equal(headers.get("referrer-policy"), "no-referrer");
  assert.equal(headers.get("x-content-type-options"), "nosniff");
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
  assert.match(scanner, /event\.key !== "Escape"/);
  assert.match(scanner, /addEventListener\("keydown", closeOnEscape\)/);
  assert.match(scanner, /removeEventListener\("keydown", closeOnEscape\)/);
  assert.match(scanner, /aria-keyshortcuts="Escape"/);
  assert.match(scanner, /scannerRef\.current\?\.destroy\(\)/);
  assert.doesNotMatch(scanner, /\bfetch\(|XMLHttpRequest|WebSocket|geolocation/);
  assert.match(styles, /\.result-secondary small\s*\{[^}]*color:\s*var\(--quiet\)/s);
  assert.match(styles, /\.http-warning\s*\{[^}]*color:\s*#ffd98a/s);
  assert.match(notices, /qr-scanner 1\.4\.2/);
});

test("opens decoded links without replacing the QR Scanner page", async () => {
  const resultView = await readFile(new URL("app/QrResultView.tsx", root), "utf8");

  assert.match(resultView, /Open link in new tab/);
  assert.match(resultView, /window\.open\(result\.href, "_blank", "noopener,noreferrer"\)/);
  assert.match(resultView, /onClick=\{openInNewTab\}/);
  assert.doesNotMatch(resultView, /window\.location\.(?:assign|replace)/);
  assert.doesNotMatch(resultView, /Open on this phone/);
  assert.match(resultView, /Scan the pairing QR shown on your PC/);
  assert.match(resultView, /isMobileClient/);
  assert.doesNotMatch(resultView, /Pair a PC first/);
});
