import assert from "node:assert/strict";
import test from "node:test";
import { renderResult } from "./result-render.mjs";

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
});
