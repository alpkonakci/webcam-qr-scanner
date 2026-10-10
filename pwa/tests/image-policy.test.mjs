import assert from "node:assert/strict";
import test from "node:test";
import { cropPixels, inspectQrImage, MAX_IMAGE_BYTES, validateImageSize } from "../lib/image-policy.mjs";

const arrayBuffer = (buffer) => buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
function png(width = 1080, height = 1920, animated = false) {
  const chunk = (name, data = Buffer.alloc(0)) => {
    const result = Buffer.alloc(12 + data.length);
    result.writeUInt32BE(data.length); result.write(name, 4); data.copy(result, 8); return result;
  };
  const header = Buffer.alloc(13); header.writeUInt32BE(width); header.writeUInt32BE(height, 4);
  return arrayBuffer(Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]), chunk("IHDR", header),
    ...(animated ? [chunk("acTL", Buffer.alloc(8))] : []), chunk("IEND")]));
}
function jpeg(width = 1080, height = 1920) {
  const bytes = Buffer.from([255,216,255,224,0,4,0,0,255,194,0,8,8,0,0,0,0,1,255,217]);
  bytes.writeUInt16BE(height, 13); bytes.writeUInt16BE(width, 15); return arrayBuffer(bytes);
}
function webp(animated = false) {
  const bytes = Buffer.alloc(30); bytes.write("RIFF"); bytes.writeUInt32LE(22, 4); bytes.write("WEBPVP8X", 8);
  bytes.writeUInt32LE(10, 16); bytes[20] = animated ? 2 : 0;
  bytes.writeUIntLE(1079, 24, 3); bytes.writeUIntLE(1919, 27, 3); return arrayBuffer(bytes);
}

test("identifies PNG/JPEG/WebP from bytes, not MIME or filename", () => {
  for (const [buffer, mime] of [[png(), "image/png"], [jpeg(), "image/jpeg"], [webp(), "image/webp"]]) {
    assert.deepEqual(inspectQrImage(buffer), { width: 1080, height: 1920, mime });
  }
});
test("rejects empty, oversized, SVG, GIF and arbitrary documents", () => {
  assert.throws(() => inspectQrImage(new ArrayBuffer(0)), /10 MB/);
  assert.throws(() => inspectQrImage(new ArrayBuffer(MAX_IMAGE_BYTES + 1)), /10 MB/);
  for (const data of ["<svg></svg>", "GIF89a", "%PDF-1.7", "plain text"]) {
    assert.throws(() => inspectQrImage(arrayBuffer(Buffer.from(data))), /not supported/);
  }
});
test("rejects animated PNG and WebP before browser decoding", () => {
  assert.throws(() => inspectQrImage(png(200, 200, true)), /animated/);
  assert.throws(() => inspectQrImage(webp(true)), /animated/);
});
test("pixel and side limits stop large image allocations", () => {
  assert.throws(() => inspectQrImage(png(5000, 5000)), /too large/);
  assert.throws(() => inspectQrImage(jpeg(9000, 100)), /too large/);
  for (const width of [0, -1, NaN, Infinity, 1.5]) assert.throws(() => validateImageSize(width, 100), /damaged/);
  assert.deepEqual(validateImageSize(2160, 3840), { width: 2160, height: 3840 });
});
test("rejects truncated and corrupt headers safely", () => {
  const valid = png();
  assert.throws(() => inspectQrImage(valid.slice(0, valid.byteLength - 1)), /damaged/);
  const broken = Buffer.from(valid); broken.writeUInt32BE(0xffffffff, 8);
  assert.throws(() => inspectQrImage(arrayBuffer(broken)), /damaged/);
  assert.throws(() => inspectQrImage(arrayBuffer(Buffer.from([255,216,255,224,255,255]))), /damaged/);
  const badWebp = Buffer.from(webp()); badWebp.writeUInt32LE(0xffffffff, 16);
  assert.throws(() => inspectQrImage(arrayBuffer(badWebp)), /damaged/);
});
test("crop uses original pixels and clamps rounding at image boundaries", () => {
  assert.deepEqual(cropPixels({ x: .25, y: .5, width: .5, height: .25 }, 1000, 2000),
    { x: 250, y: 1000, width: 500, height: 500 });
  assert.deepEqual(cropPixels({ x: 0, y: 0, width: 1, height: 1 }, 1080, 1920),
    { x: 0, y: 0, width: 1080, height: 1920 });
});
test("missing, tiny, outside and non-finite crops are rejected", () => {
  for (const crop of [null, {x:0,y:0,width:0,height:1}, {x:-.1,y:0,width:1,height:1},
    {x:.5,y:0,width:1,height:1}, {x:0,y:NaN,width:1,height:1}]) {
    assert.throws(() => cropPixels(crop, 100, 100), /Select/);
  }
  assert.throws(() => cropPixels({x:0,y:0,width:.1,height:.1}, 100, 100), /larger area/);
});
