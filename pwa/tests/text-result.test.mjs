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
async function fixture(text, clipboard, language = "en") {
  const source = await readFile(new URL("../app/TextResultView.tsx", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS } }).outputText;
  const buttons = [], messages = [];
  let selected = false;
  const runtime = require("react/jsx-runtime");
  const captureRuntime = Object.fromEntries(Object.entries(runtime).map(([name, value]) => [name,
    name === "jsx" || name === "jsxs" ? (type, props, key) => {
      if (type === "button") buttons.push(props);
      return value(type, props, key);
    } : value,
  ]));
  const exports = {};
  runInNewContext(compiled, {
    exports, navigator: { clipboard },
    require: (name) => name === "react" ? { ...React,
      useState: (initial) => [initial, (value) => messages.push(value)],
      useRef: () => ({ current: { focus() {}, select() { selected = true; } } }),
    } : name === "../lib/i18n" ? { useLocale: () => ({ tr: (text) => translate(text, language) }) }
      : name === "react/jsx-runtime" ? captureRuntime : require(name),
  });
  const element = exports.TextResultView({ text, onScanAgain() {} });
  return { html: renderToStaticMarkup(element), buttons, messages, selected: () => selected };
}

test("text QR is escaped, read-only and has no open or send action", async () => {
  const view = await fixture("<script>alert(1)</script>\nTürkçe");
  assert.match(view.html, /&lt;script&gt;/);
  assert.doesNotMatch(view.html, /<script>|Send to PC|Open link|href=/);
  assert.match(view.html, /readOnly=""/);
  assert.deepEqual(view.buttons.map((button) => button.children), ["Copy text", "Scan another QR"]);
});

test("copy is user-triggered and preserves exact content", async () => {
  const writes = [];
  const text = "  Türkçe 😀\nSecond line  ";
  const view = await fixture(text, { writeText: async (value) => writes.push(value) });
  assert.deepEqual(writes, []);
  view.buttons[0].onClick();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(writes, [text]);
  assert.deepEqual(view.messages, ["Text copied."]);
});

test("unavailable clipboard selects text and explains manual copying", async () => {
  const view = await fixture("hello", { writeText: async () => { throw new Error("denied"); } });
  view.buttons[0].onClick();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(view.selected(), true);
  assert.match(view.messages[0], /Press and hold/);
});

test("Turkish UI preserves exact QR content and copied text", async () => {
  const text = "Back\nSend to PC\nhttps://example.com/?token=secret";
  const writes = [];
  const view = await fixture(text, { writeText: async (value) => writes.push(value) }, "tr");
  assert.match(view.html, /Metni kopyala/);
  assert.match(view.html, /Back\nSend to PC/);
  view.buttons[0].onClick();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(writes, [text]);
});
