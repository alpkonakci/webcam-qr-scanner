// Render-only fixtures: real result component markup, controlled hook state.
// These do not grant camera permission or send anything to a relay.
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
export async function renderResult(state, message) {
  const source = await readFile(new URL("../app/QrResultView.tsx", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS },
  }).outputText;
  let hook = 0;
  const controlledReact = {
    ...React,
    useState: () => [hook++ === 0 ? state : message, () => {}],
    useRef: (initial) => ({ current: initial }),
  };
  const exports = {};
  runInNewContext(compiled, {
    exports,
    require: (name) => name === "react" ? controlledReact
      : name === "../lib/relay-client" ? {} : require(name),
  });
  return renderToStaticMarkup(React.createElement(exports.QrResultView, {
    result: { ok: true, href: "https://example.com/", hostname: "example.com", insecure: false },
    pairedPc: { pcLabel: "My PC" }, isMobileClient: true,
    onPairPc() {}, onPairRevoked() {}, onScanAgain() {},
  }));
}
