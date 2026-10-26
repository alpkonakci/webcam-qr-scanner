import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const require = createRequire(import.meta.url);
const nextRequire = createRequire(require.resolve("@next/eslint-plugin-next"));
const viteRequire = createRequire(require.resolve("vite-plugin-dynamic-import"));
const glob = nextRequire("fast-glob");

async function withFixture(run) {
  const cwd = await mkdtemp(path.join(os.tmpdir(), "wqrs-glob-"));
  try {
    for (const dir of ["apps/one", "apps/two", "pages/nested"]) {
      await mkdir(path.join(cwd, dir), { recursive: true });
    }
    for (const name of ["apps/file.txt", "pages/one.js", "pages/two.ts", "pages/skip.js", "pages/.hidden.js", "pages/nested/index.js", "pages/[id].js"]) {
      await writeFile(path.join(cwd, name), "export default 1;\n");
    }
    await run(cwd);
  } finally {
    await rm(cwd, { recursive: true, force: true });
  }
}

test("both real build consumers resolve the private replacement instead of braces", () => {
  for (const consumer of [nextRequire, viteRequire]) {
    assert.equal(consumer("fast-glob/package.json").name, "@wqrs/build-glob");
    assert.equal(consumer("fast-glob/package.json").dependencies.tinyglobby, "0.2.17");
    assert.throws(() => consumer.resolve("micromatch"), { code: "MODULE_NOT_FOUND" });
    assert.throws(() => consumer.resolve("braces"), { code: "MODULE_NOT_FOUND" });
  }
});

test("Next's actual root resolver selects directories including Windows separators", async () => {
  await withFixture(async (cwd) => {
    const { getRootDirs } = require("@next/eslint-plugin-next/dist/utils/get-root-dirs.js");
    const roots = getRootDirs({ cwd, settings: { next: { rootDir: [path.join(cwd, "apps", "*"), 42] } } });
    assert.deepEqual(roots.map(p => p.replaceAll("\\", "/")).sort(),
      ["one", "two"].map(name => path.join(cwd, "apps", name).replaceAll("\\", "/")).sort());
    assert.deepEqual(getRootDirs({ cwd, settings: {} }), [cwd]);
  });
});

test("Vite consumer preserves extension alternatives, exclusions and default file matching", async () => {
  await withFixture(async (cwd) => {
    const viteGlob = viteRequire("fast-glob");
    const patterns = ["pages/**/*.{js,ts}", "!pages/skip.js"];
    const expected = ["pages/[id].js", "pages/nested/index.js", "pages/one.js", "pages/two.ts"];
    assert.deepEqual(viteGlob.sync(patterns, { cwd }).sort(), expected);
    assert.deepEqual((await glob(patterns, { cwd })).sort(), expected);
    assert.deepEqual(glob.sync("pages", { cwd }), []);
    assert.deepEqual(glob.sync("pages/\\[id\\].js", { cwd }), ["pages/[id].js"]);
    assert.deepEqual(glob.sync("pages/*.js", { cwd, ignore: "**/skip.js" }).sort(), ["pages/[id].js", "pages/one.js"]);
  });
});

test("Vite's actual dynamic import expansion uses the replacement", async () => {
  await withFixture(async (cwd) => {
    const { parse } = await import("acorn");
    const { globFiles } = await import("vite-plugin-dynamic-import");
    const expression = 'import(`./pages/${name}.js`)';
    const ast = parse(expression, { ecmaVersion: "latest", sourceType: "module" });
    const { files } = await globFiles({
      importeeNode: ast.body[0].expression.source,
      importExpression: expression,
      importer: path.join(cwd, "main.js"),
      resolve: { tryResolve: async () => undefined },
      extensions: [".js", ".ts"],
    });
    assert.deepEqual(files.sort(), ["./pages/[id].js", "./pages/nested/index.js", "./pages/one.js", "./pages/skip.js"]);
  });
});

test("deep, malformed and oversized patterns fail before the glob engine runs", async () => {
  for (const pattern of ["{".repeat(3500) + "x" + "}".repeat(3500), "{)".repeat(100), "a".repeat(8193)]) {
    assert.throws(() => glob.sync(pattern), /nesting|length/);
    await assert.rejects(glob(pattern), /nesting|length/);
    assert.throws(() => glob.sync("*.js", { ignore: pattern }), /nesting|length/);
  }
  assert.throws(() => glob.sync(Array(1025).fill("*.js")), /1024/);
  assert.throws(() => glob.sync("*.js", { objectMode: true }), /Unsupported/);
});
