// Mechanical JSX-literal migration. Dynamic payload values stay verbatim.
import ts from "typescript";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
const root = new URL("../", import.meta.url);
const catalog = JSON.parse(readFileSync(new URL("lib/translations.tr.json", root), "utf8"));
for (const name of ["PwaHome", "QrResultView", "PairingView", "QrScannerView", "QrImageView", "TextResultView"]) {
  const path = new URL(`app/${name}.tsx`, root);
  let source = readFileSync(path, "utf8");
  const parsed = ts.createSourceFile(fileURLToPath(path), source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const edits = [];
  const normal = (value) => value.replaceAll("&apos;", "'").replaceAll("&amp;", "&").replace(/\s+/g, " ").trim();
  function visit(node) {
    if (ts.isJsxText(node) && catalog[normal(node.text)]) {
      edits.push([node.getStart(parsed), node.end, `{tr(${JSON.stringify(normal(node.text))})}`]);
    } else if (ts.isStringLiteral(node) && catalog[normal(node.text)]) {
      let parent = node.parent, inJsx = false, excluded = false;
      while (parent) {
        if (ts.isJsxExpression(parent)) inJsx = true;
        if (ts.isCallExpression(parent) && parent.expression.getText(parsed) === "tr") excluded = true;
        parent = parent.parent;
      }
      if (ts.isJsxAttribute(node.parent) && ["aria-label", "title", "alt"].includes(node.parent.name.getText(parsed))) {
        edits.push([node.getStart(parsed), node.end, `{tr(${JSON.stringify(normal(node.text))})}`]);
      } else if (inJsx && !excluded) edits.push([node.getStart(parsed), node.end, `tr(${JSON.stringify(normal(node.text))})`]);
    }
    ts.forEachChild(node, visit);
  }
  visit(parsed);
  for (const [start, end, value] of edits.sort((a,b) => b[0] - a[0])) source = source.slice(0,start) + value + source.slice(end);
  if (!source.includes('useLocale } from "../lib/i18n"')) source = source.replace('"use client";', '"use client";\nimport { useLocale } from "../lib/i18n";');
  if (!source.includes("const { tr } = useLocale();")) {
    const declaration = source.indexOf(`export function ${name}(`);
    // JSX component signatures end at ') {'; object prop type bodies can
    // contain braces, so don't pick the first opening brace in the signature.
    const bodyStart = source.indexOf(") {", declaration) + 3;
    source = source.slice(0,bodyStart) + "\n  const { tr } = useLocale();" + source.slice(bodyStart);
  }
  source = source.replaceAll('{tr("Continue with")}', '{tr("Continue with")} ')
    .replaceAll('{tr("Replacing")}', '{tr("Replacing")} ');
  writeFileSync(path, source);
  console.log(name, edits.length, "UI literals migrated");
}
