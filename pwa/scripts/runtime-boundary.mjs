import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const projectRoot = fileURLToPath(new URL("../", import.meta.url));
const sourceRoots = ["app", "lib", "server", "worker"];
// Installed packages flagged by the current braces advisory, not every glob
// implementation or every possible future dependency vulnerability.
const toolPackages = [
  "braces", "micromatch", "fast-glob", "@next/eslint-plugin-next",
  "eslint-config-next", "vite-plugin-dynamic-import", "vite-plugin-commonjs",
];

export function assertRuntimeSpecifier(specifier, filename, root = projectRoot) {
  if (toolPackages.some((name) => specifier === name || specifier.startsWith(`${name}/`))) {
    throw new Error(`Build-only dependency in runtime source: ${specifier} (${filename})`);
  }
  // The Worker uses vinext server entry points, not its root Vite plugin.
  if (specifier === "vinext" || (specifier.startsWith("vinext/") && !specifier.startsWith("vinext/server/"))) {
    throw new Error(`vinext build entry in runtime source: ${specifier} (${filename})`);
  }
  if (specifier.startsWith(".") || specifier.startsWith("@/")) {
    const target = specifier.startsWith("@/")
      ? path.resolve(root, specifier.slice(2))
      : path.resolve(path.dirname(filename), specifier);
    const relative = path.relative(root, target).replaceAll("\\", "/");
    if (!sourceRoots.some((name) => relative.startsWith(`${name}/`))) {
      throw new Error(`Runtime import leaves reviewed source roots: ${specifier} (${filename})`);
    }
  }
}

export function assertRuntimeSource(source, filename, root = projectRoot) {
  const ast = ts.createSourceFile(filename, source, ts.ScriptTarget.Latest, true);
  function checkLiteral(node) {
    if (!node || !ts.isStringLiteralLike(node)) {
      throw new Error(`Computed runtime module loading requires review (${filename})`);
    }
    assertRuntimeSpecifier(node.text, filename, root);
  }
  function visit(node) {
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier) {
      checkLiteral(node.moduleSpecifier);
    }
    if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)) {
      checkLiteral(node.moduleReference.expression);
    }
    if (ts.isCallExpression(node)) {
      const expression = node.expression;
      if (expression.kind === ts.SyntaxKind.ImportKeyword ||
          (ts.isIdentifier(expression) && expression.text === "require") ||
          (ts.isPropertyAccessExpression(expression) && expression.getText(ast) === "require.resolve")) {
        checkLiteral(node.arguments[0]);
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(ast);
}

async function filesUnder(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const filename = path.join(directory, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`Unreviewed symlink: ${filename}`);
    if (entry.isDirectory()) files.push(...await filesUnder(filename));
    else if (entry.isFile()) files.push(filename);
  }
  return files;
}

export async function checkRuntimeSources(root = projectRoot) {
  let checked = 0;
  for (const directory of sourceRoots) {
    for (const filename of await filesUnder(path.join(root, directory))) {
      if (!/\.(?:[cm]?[jt]s|[jt]sx)$/.test(filename)) continue;
      assertRuntimeSource(await readFile(filename, "utf8"), filename, root);
      checked++;
    }
  }
  if (!checked) throw new Error("No runtime sources checked");
  return checked;
}

export function assertRuntimeModuleId(id) {
  const normalized = id.replaceAll("\\", "/");
  if (toolPackages.some((name) => normalized === name || normalized.startsWith(`${name}/`) || normalized.includes(`/node_modules/${name}/`)) ||
      normalized === "vinext" ||
      /\/node_modules\/vinext\/dist\/index\.[cm]?js(?:$|\?)/.test(normalized)) {
    throw new Error(`Build-only dependency in runtime artifact: ${id}`);
  }
}

export async function checkNextTraces(root = projectRoot) {
  const traces = (await filesUnder(path.join(root, ".next/server")))
    .filter((filename) => filename.endsWith(".nft.json"));
  if (!traces.length) throw new Error("Next runtime traces missing; run the production build first");
  for (const filename of traces) {
    const trace = JSON.parse(await readFile(filename, "utf8"));
    if (!Array.isArray(trace.files)) throw new Error(`Invalid Next trace: ${filename}`);
    for (const dependency of trace.files) {
      if (typeof dependency !== "string") throw new Error(`Invalid trace dependency: ${filename}`);
      assertRuntimeModuleId(path.resolve(path.dirname(filename), dependency));
    }
  }
  return traces.length;
}

// Vite module IDs include code bundled into chunks, unlike a text search of the
// minified output. Build tool execution itself is intentionally not blocked.
export function runtimeBoundaryPlugin() {
  return {
    name: "wqrs-runtime-boundary",
    apply: "build",
    async buildStart() { await checkRuntimeSources(); },
    generateBundle() {
      for (const id of this.getModuleIds()) assertRuntimeModuleId(id);
    },
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const sourceCount = await checkRuntimeSources();
    const traceCount = process.argv.includes("--next-traces") ? await checkNextTraces() : null;
    console.log(`Runtime boundary passed: ${sourceCount} sources${traceCount === null ? "" : `, ${traceCount} Next traces`}`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
