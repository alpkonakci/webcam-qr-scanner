import type { WebUrlResult } from "./url-policy.mjs";

export type QrPayloadResult =
  | { kind: "link"; result: WebUrlResult }
  | { kind: "text"; text: string };

export function parseQrPayload(value: unknown): QrPayloadResult;
