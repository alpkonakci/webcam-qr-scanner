import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  assertRuntimeModuleId, assertRuntimeSource, assertRuntimeSpecifier,
  checkNextTraces, checkRuntimeSources, runtimeBoundaryPlugin,
} from "../scripts/runtime-boundary.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const filename = path.join(root, "app", "fixture.tsx");

test("runtime source and built Next traces exclude the reported dev-only chain", async () => {
  assert.ok(await checkRuntimeSources() > 0);
  assert.ok(await checkNextTraces() > 0);
});

test("the source gate detects static, re-exported, dynamic and CJS tool imports", () => {
  for (const source of [
    'import x from "braces";', 'export { x } from "micromatch";',
    'import("fast-glob");', 'require("eslint-config-next/core-web-vitals");',
    'import x = require("vite-plugin-commonjs");',
    'require.resolve("@next/eslint-plugin-next");',
    'import x from "bra\\u0063es";', 'import x from "vinext";',
  ]) assert.throws(() => assertRuntimeSource(source, filename), /Build-only|build entry/);
});

test("computed module loading and local imports of build helpers require review", () => {
  for (const source of ['import(qrValue);', 'require(qrValue);', 'import(`./${qrValue}`);']) {
    assert.throws(() => assertRuntimeSource(source, filename), /requires review/);
  }
  for (const specifier of ["../build/sites-vite-plugin", "@/scripts/runtime-boundary.mjs", "../../outside"]) {
    assert.throws(() => assertRuntimeSpecifier(specifier, filename), /leaves reviewed/);
  }
});

test("normal QR imports, local runtime modules and Worker server entry points stay allowed", () => {
  assert.doesNotThrow(() => assertRuntimeSource(
    'import("qr-scanner"); import x from "../lib/wqrs"; import y from "@/server/relay-handler"; import z from "vinext/server/app-router-entry";', filename,
  ));
});

test("artifact gate detects Windows, nested and external module IDs without blocking the Worker runtime", () => {
  for (const id of [
    "fast-glob", "braces/lib/parse.js",
    "C:\\project\\node_modules\\braces\\index.js",
    "/project/node_modules/x/node_modules/micromatch/index.js",
    "/project/node_modules/vinext/dist/index.js?commonjs-proxy",
  ]) assert.throws(() => assertRuntimeModuleId(id), /runtime artifact/);
  assert.doesNotThrow(() => assertRuntimeModuleId("/project/node_modules/vinext/dist/server/app-router-entry.js"));
  const plugin = runtimeBoundaryPlugin();
  assert.throws(() => plugin.generateBundle.call({
    getModuleIds: () => ["/project/node_modules/fast-glob/out/index.js"][Symbol.iterator](),
  }), /runtime artifact/);
});
