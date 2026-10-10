import assert from "node:assert/strict";
import test from "node:test";
import { renderResult, resultFixture } from "./result-render.mjs";

test("rendered pending/checking results disable sending and expose receipt-only checks", async () => {
  const pending = await renderResult("pending", "Delivery is not confirmed yet. This link may still arrive.");
  assert.match(pending, /disabled=""[^>]*><span>Awaiting receipt/);
  assert.match(pending, /Check delivery status/);
  assert.match(pending, /No new link will be sent/);
  assert.match(pending, /role="status"/);
  assert.doesNotMatch(pending, /role="alert"/);
  const checking = await renderResult("checking", "Checking the existing delivery...");
  assert.match(checking, /disabled=""[^>]*><span>Checking\.\.\./);
  const delivered = await renderResult("delivered", "My PC received and verified the link.");
  assert.match(delivered, /disabled=""[^>]*><span>Received by PC/);
  assert.doesNotMatch(delivered, /Check delivery status/);
  assert.match(delivered, /You can scan the same QR again to send it once more/);
  const unconfirmed = await renderResult("unconfirmed", "The receipt is no longer available. Check your PC.");
  assert.match(unconfirmed, /disabled=""[^>]*><span>Check your PC/);
  assert.doesNotMatch(unconfirmed, /Check delivery status|Received by PC/);
});

test("explicit scan-again waits for rearming and guards repeated taps", async () => {
  let prepared = 0;
  let scanned = 0;
  let release;
  const waiting = new Promise((resolve) => { release = resolve; });
  const fixture = await resultFixture("delivered", "Received", {
    prepareUrlRescan: async (pc, url) => {
      assert.equal(pc.pcLabel, "My PC");
      assert.equal(url, "https://example.com/");
      prepared += 1;
      await waiting;
      return true;
    },
  }, () => { scanned += 1; });
  const scanButton = fixture.buttons.find((button) => button.className === "result-text-button");
  assert.equal(scanButton.disabled, false);
  scanButton.onClick();
  scanButton.onClick();
  assert.equal(prepared, 1);
  assert.equal(scanned, 0);
  release();
  await new Promise(setImmediate);
  assert.equal(scanned, 1);
});

test("pending scan-again preserves the attempt and sending disables scan-again", async () => {
  let scanned = 0;
  const pending = await resultFixture("pending", "Awaiting receipt", {
    prepareUrlRescan: async () => false,
  }, () => { scanned += 1; });
  pending.buttons.find((button) => button.className === "result-text-button").onClick();
  await new Promise(setImmediate);
  assert.equal(scanned, 1);
  for (const state of ["sending", "checking"]) {
    const busy = await resultFixture(state, "Waiting");
    assert.equal(busy.buttons.find((button) => button.className === "result-text-button").disabled, true);
  }
});
