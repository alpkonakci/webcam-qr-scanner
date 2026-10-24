import assert from "node:assert/strict";
import test from "node:test";
import { adjustSelection } from "../lib/keyboard-crop.ts";

test("keyboard area fields stay within the original image and ignore invalid input", () => {
  const moved = adjustSelection(null, "x", 80);
  assert.deepEqual(moved, { x: .8, y: 0, width: .2, height: 1 });
  const narrowed = adjustSelection(moved, "height", 25);
  assert.deepEqual(narrowed, { x: .8, y: 0, width: .2, height: .25 });
  assert.deepEqual(adjustSelection(narrowed, "width", Number.NaN), narrowed);
  assert.deepEqual(adjustSelection(null, "y", 500), { x: 0, y: .99, width: 1, height: .01 });
});
