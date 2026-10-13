// Real result component markup/handlers with controlled hook state.
// These do not grant camera permission or send anything to a relay.
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
export async function resultFixture(state, message, relayClient = {}, onScanAgain = () => {}) {
  const source = await readFile(new URL("../app/QrResultView.tsx", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS },
  }).outputText;
  let hook = 0;
  const controlledReact = {
    ...React,
    useState: () => [hook++ === 0 ? state : message, () => {}],
    useRef: (initial) => ({ current: initial }),
    useEffect: () => {},
  };
  const buttons = [];
  const runtime = require("react/jsx-runtime");
  const captureRuntime = Object.fromEntries(Object.entries(runtime).map(([name, value]) => [name,
    name === "jsx" || name === "jsxs" ? (type, props, key) => {
      if (type === "button") buttons.push(props);
      return value(type, props, key);
    } : value,
  ]));
  const exports = {};
  runInNewContext(compiled, {
    exports,
    require: (name) => name === "react" ? controlledReact
      : name === "../lib/relay-client" ? relayClient
      : name === "react/jsx-runtime" ? captureRuntime : require(name),
  });
  const element = exports.QrResultView({
    result: { ok: true, href: "https://example.com/", hostname: "example.com", insecure: false },
    pairedPc: { pcLabel: "My PC" }, isMobileClient: true,
    onPairPc() {}, onPairRevoked() {}, onScanAgain,
  });
  return { element, buttons };
}

export async function renderResult(state, message) {
  return renderToStaticMarkup((await resultFixture(state, message)).element);
}
