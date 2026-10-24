import assert from "node:assert/strict";
import test from "node:test";
import { pastedImage, readClipboardImage } from "../lib/image-clipboard.mjs";

test("paste accepts one local image and never follows copied links or HTML", () => {
  const image = new Blob(["test"], {type:"image/png"});
  assert.equal(pastedImage({files:[image]}), image);
  assert.throws(() => pastedImage({files:[], getData:() => "https://example.com/image.png"}), /image itself/);
  assert.throws(() => pastedImage({files:[image,image]}), /one image/);
});
test("clipboard uses one preferred image representation, not HTML or text", async () => {
  const image = new Blob(["test"], {type:"image/png"});
  const requested = [];
  const clipboard = {read:async () => [{types:["text/html","image/jpeg","image/png"], getType:async type => {requested.push(type); return image;}}]};
  assert.equal(await readClipboardImage(clipboard, new AbortController().signal), image);
  assert.deepEqual(requested, ["image/png"]);
});
test("unsupported, text-only and multiple image clipboard contents give guidance", async () => {
  const signal = new AbortController().signal;
  await assert.rejects(readClipboardImage(undefined, signal), /Ctrl\+V/);
  for (const [types,error] of [[["text/html"], /image itself/], [["image/svg+xml"], /not supported/]]) {
    await assert.rejects(readClipboardImage({read:async () => [{types}]}, signal), error);
  }
  await assert.rejects(readClipboardImage({read:async () => [{types:["image/png"]},{types:["image/jpeg"]}]}, signal), /one image/);
});
test("permission denial is preserved for the user-facing fallback", async () => {
  await assert.rejects(readClipboardImage({read:async () => {throw new DOMException("denied","NotAllowedError");}}, new AbortController().signal), {name:"NotAllowedError"});
});
test("aborting clipboard access ignores a late response and reads no image", async () => {
  const controller = new AbortController();
  let release, reads = 0;
  const pending = readClipboardImage({read:() => new Promise(resolve => {release = resolve;})}, controller.signal);
  controller.abort();
  await assert.rejects(pending, {name:"AbortError"});
  release([{types:["image/png"],getType:() => {reads++;}}]);
  await new Promise(resolve => setTimeout(resolve,0));
  assert.equal(reads,0);
});
test("pre-aborted requests never access the clipboard", async () => {
  const controller = new AbortController(); controller.abort();
  await assert.rejects(readClipboardImage({read:() => {throw new Error("must not read");}},controller.signal), {name:"AbortError"});
});
