import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);

test("the scoped esbuild security override still transforms TypeScript", () => {
  const fromCoreUtils = createRequire(require.resolve("@esbuild-kit/core-utils"));
  const esbuild = fromCoreUtils("esbuild");
  const output = esbuild.transformSync("const value: number = 1", { loader: "ts" });
  assert.match(output.code, /const value = 1/);
  assert.doesNotMatch(output.code, /: number/);
});

test("the fflate override preserves font-loader decompression", () => {
  const fromSatori = createRequire(require.resolve("satori"));
  const fflate = fromSatori("fflate");
  const input = new TextEncoder().encode("synthetic font-loader compatibility input");
  assert.deepEqual(fflate.unzlibSync(fflate.zlibSync(input)), input);
});

test("the sharp security patch can encode an in-memory image", async () => {
  const sharp = require("sharp");
  const output = await sharp({
    create: { width: 2, height: 2, channels: 3, background: "#ffffff" },
  }).png().toBuffer();
  const metadata = await sharp(output).metadata();
  assert.equal(metadata.format, "png");
  assert.equal(metadata.width, 2);
  assert.equal(metadata.height, 2);
});
