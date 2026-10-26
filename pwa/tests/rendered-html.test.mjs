import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const root = new URL("../", import.meta.url);
const require = createRequire(import.meta.url);

function renderHome() {
  const { buildSync } = require("esbuild");
  const build = buildSync({
    entryPoints: [fileURLToPath(new URL("app/PwaHome.tsx", root))],
    bundle: true, write: false, platform: "node", format: "cjs", packages: "external", jsx: "automatic",
  });
  const compiledModule = { exports: {} };
  runInNewContext(build.outputFiles[0].text, { module: compiledModule, exports: compiledModule.exports, require });
  return renderToStaticMarkup(React.createElement(compiledModule.exports.PwaHome));
}

test("Turkish receipt labels distinguish delivery from opening the browser", async () => {
  const { renderResult } = await import("./result-render.mjs");
  const pending = await renderResult("pending", "Delivery is not confirmed yet.", "tr");
  assert.match(pending, /PC&#x27;nin alması bekleniyor/);
  assert.doesNotMatch(pending, /PC aldı/);
  const received = await renderResult("delivered", "My PC received and verified the link.", "tr");
  assert.match(received, /PC aldı/);
  assert.match(received, /Açılması için PC&#x27;de onay vermen gerekir/);
  assert.match(received, /https:\/\/example.com\//);
});

test("renders the QR Scanner shell with user-triggered scan actions", () => {
  const home = renderHome();
  assert.match(home, /QR Scanner/);
  assert.match(home, /Scan a QR\./);
  assert.match(home, /On-device QR reading/);
  assert.match(home, /aria-label="Settings and about"/);
  assert.match(home, /class="settings-toggle"/);
  assert.match(home, /Scan a link, text or PC pairing code/);
  assert.match(home, /Read from image/);
  assert.match(home, /No location access/);
  assert.doesNotMatch(home, /<video|role="dialog"|image-reader-heading/);
  assert.doesNotMatch(home, /Coming next|codex-preview|react-loading-skeleton|Your site is taking shape/i);
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
  assert.match(csp, /img-src 'self' data: blob:/);
  const scripts = csp.split(";").find(value => value.trim().startsWith("script-src "));
  assert.doesNotMatch(scripts, /'unsafe-inline'/);
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
  const [resultView, home] = await Promise.all([
    readFile(new URL("app/QrResultView.tsx", root), "utf8"),
    readFile(new URL("app/PwaHome.tsx", root), "utf8"),
  ]);

  assert.match(resultView, /Open link in new tab/);
  assert.match(resultView, /window\.open\(result\.href, "_blank", "noopener,noreferrer"\)/);
  assert.match(resultView, /onClick=\{openInNewTab\}/);
  assert.doesNotMatch(resultView, /window\.location\.(?:assign|replace)/);
  assert.match(resultView, /Scan the pairing QR shown on your PC/);
  assert.match(resultView, /isMobileClient/);
  assert.doesNotMatch(resultView, /Pair a PC first/);
  assert.match(resultView, /isPairRevokedError\(error\)/);
  assert.match(resultView, /removePairIfRevoked\(error, pairedPc\.pairId\)/);
  assert.match(resultView, /Pair a PC again to keep using Send to PC/);
  assert.match(home, /onPairRevoked=\{clearRevokedPair\}/);
  assert.match(home, /current\?\.pairId === pairId \? null : current/);
});

test("explains how to return without replacing the saved phone pairing", async () => {
  const home = await readFile(new URL("app/PwaHome.tsx", root), "utf8");
  assert.match(home, /Your connection is saved in this browser/);
  assert.match(home, /Bookmark this page/);
  assert.match(home, /Closing the tab does not/);
  assert.match(home, /Open scanner/);
  assert.match(home, /normal camera opens websites directly/);
  assert.match(home, /same browser/);
  assert.doesNotMatch(home, /navigator\.clipboard|localStorage\.setItem/);
});

test("uses the desktop QR as the only pairing confirmation", async () => {
  const pairingView = await readFile(
    new URL("app/PairingView.tsx", root),
    "utf8",
  );

  assert.match(pairingView, /automaticPairingStarted/);
  assert.match(pairingView, /void beginPairing\(\)/);
  assert.match(pairingView, /samePcAlreadyPaired/);
  assert.doesNotMatch(pairingView, /Returning to QR Scanner/);
  assert.match(
    pairingView,
    /const cancelUnusedPairing = useCallback\(\(\) => \{\s*onCancel\(\);\s*void cancelPairingFromPhone/s,
  );
  assert.doesNotMatch(pairingView, /Pair this phone\?/);
  assert.doesNotMatch(pairingView, /Waiting for PC approval/);
});

test("pending receipts have a GET-only check action and duplicate-tap guard", async () => {
  const resultView = await readFile(new URL("app/QrResultView.tsx", root), "utf8");
  assert.match(resultView, /error instanceof PendingDeliveryError/);
  assert.match(resultView, /setDeliveryState\("pending"\)/);
  assert.match(resultView, /await checkUrlDelivery\(pairedPc, result.href, controller.signal\)/);
  assert.match(resultView, /watchUrlDelivery\(pairedPc, result.href, controller.signal\)/);
  assert.match(resultView, /deliveryBusy.current/);
  assert.match(resultView, /Check delivery status/);
  assert.match(resultView, /No new link will be sent/);
  assert.match(resultView, /disabled=\{[^}]*deliveryState === "pending"/);
});

test("camera permission help is site-specific and refresh does not auto-open the camera", async () => {
  const home = await readFile(new URL("app/PwaHome.tsx", root), "utf8");
  assert.match(home, /\[scannerOpen, setScannerOpen\] = useState\(false\)/);
  assert.match(home, /Camera permission after refreshing/);
  assert.match(home, /You do not need to allow all websites/);
  assert.match(home, /Camera permission is separate from your saved PC pairing/);
});
