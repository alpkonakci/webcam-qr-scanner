import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { translate } from "../lib/i18n-core.ts";

const require = createRequire(import.meta.url);
const source = await readFile(new URL("../app/HomeScreenGuide.tsx", import.meta.url), "utf8");
const exports = {};
runInNewContext(ts.transpileModule(source, {compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS}}).outputText, {exports, require});
const render = (installed, pairing, language = "en") => renderToStaticMarkup(React.createElement(exports.HomeScreenGuide, {
  context:{platform:"ios",installed}, pairing, tr:(text)=>translate(text, language),
}));

test("iPhone guide uses Apple's steps and never promises to transfer stored keys", () => {
  const html = render(false, "available", "tr");
  assert.match(html, /Ana Ekrana Ekle/);
  assert.match(html, /support\.apple\.com/);
  assert.match(html, /kopyalanmasını garanti etmez/);
  assert.doesNotMatch(html, /senderToken|rootKey|#pair|\?token=/);
});
test("installed mode explains separate storage and offers safe pairing recovery", () => {
  const html = render(true, "missing");
  assert.match(html, /Using the Home Screen app/);
  assert.match(html, /original browser pairing is not deleted/);
  assert.match(html, /No saved PC is available/);
  assert.doesNotMatch(html, /<ol>/);
});
test("a failed storage read is not presented as proof that no pairing exists", () => {
  const html = render(true, "unavailable");
  assert.match(html, /role="alert"/);
  assert.match(html, /storage could not be read/);
  assert.doesNotMatch(html, /No saved PC is available/);
});
