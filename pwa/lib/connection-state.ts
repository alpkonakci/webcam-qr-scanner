import type { PcConnection } from "./relay-client.ts";
export function freshConnection(value: PcConnection | null, freshUntilMs: number, nowMs: number): PcConnection["state"] {
  if (!value || value.pairStatus !== "active") return "unknown";
  if (value.state === "reachable" && nowMs >= freshUntilMs) return "unknown";
  return value.state;
}
