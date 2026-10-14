import assert from "node:assert/strict";
import test from "node:test";
import { homeScreenContext } from "../lib/home-screen.ts";
import { IDBFactory } from "fake-indexeddb";
import { savePair, getMostRecentPair } from "../lib/pair-store.ts";

test("pairing survives reopening the same store but is not exported into an isolated installed-app store", async (context) => {
  const original = globalThis.indexedDB;
  context.after(() => { Object.defineProperty(globalThis, "indexedDB", { value: original, configurable: true }); });
  const browser = new IDBFactory();
  Object.defineProperty(globalThis, "indexedDB", { value: browser, configurable: true });
  const rootKey = await crypto.subtle.importKey("raw", new Uint8Array(32), "HKDF", false, ["deriveKey"]);
  await savePair({ relayOrigin: "https://qrwebcam.vercel.app", deviceId: "B".repeat(22), pairId: "A".repeat(22),
    senderToken: "C".repeat(43), rootKey, pcLabel: "Test PC", keyEpoch: 1, pairedAt: 1700000000 });
  const reopened = await getMostRecentPair();
  assert.equal(reopened?.pcLabel, "Test PC");
  assert.equal(reopened?.rootKey.extractable, false);
  await assert.rejects(crypto.subtle.exportKey("raw", reopened!.rootKey));
  Object.defineProperty(globalThis, "indexedDB", { value: new IDBFactory(), configurable: true });
  assert.equal(await getMostRecentPair(), null);
  Object.defineProperty(globalThis, "indexedDB", { value: browser, configurable: true });
  assert.equal((await getMostRecentPair())?.pcLabel, "Test PC");
});

test("home-screen guidance distinguishes installation mode without claiming a pairing transfer", () => {
  assert.deepEqual(homeScreenContext({ userAgent: "iPhone", platform: "iPhone", maxTouchPoints: 5, standalone: false }), { platform: "ios", installed: false });
  assert.deepEqual(homeScreenContext({ userAgent: "Macintosh", platform: "MacIntel", maxTouchPoints: 5, standalone: true }), { platform: "ios", installed: true });
  assert.deepEqual(homeScreenContext({ userAgent: "Android Chrome", platform: "Linux", maxTouchPoints: 5, standalone: false }), { platform: "android", installed: false });
});
