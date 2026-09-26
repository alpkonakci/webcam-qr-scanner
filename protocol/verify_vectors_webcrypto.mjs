import { readFile } from "node:fs/promises";

import { verifyWqrsVector } from "./webcrypto_conformance.mjs";


const vectorUrl = new URL("./test-vectors/wqrs-1.json", import.meta.url);
const vector = JSON.parse(await readFile(vectorUrl, "utf8"));

await verifyWqrsVector(vector);
console.log("WQRS/1 vectors verified with the browser-compatible WebCrypto API.");

