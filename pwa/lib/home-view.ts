import type { QrPayloadResult } from "./qr-payload.mjs";
import type { WebUrlResult } from "./url-policy.mjs";

type HomeView =
  | { kind: "home" | "settings" | "image"; titleId: string }
  | { kind: "pairing"; titleId: string; uri: string }
  | { kind: "text"; titleId: string; text: string }
  | { kind: "link"; titleId: string; result: WebUrlResult };

interface ViewState {
  settingsOpen: boolean;
  imageOpen: boolean;
  pairingUri: string | null;
  scanResult: QrPayloadResult | null;
}

// The camera is an overlay; this selects the content beneath it. Keep the
// content and its accessible heading together so their precedence cannot drift.
export function selectHomeView(state: ViewState): HomeView {
  if (state.settingsOpen) return { kind: "settings", titleId: "settings-title" };
  if (state.imageOpen) return { kind: "image", titleId: "image-reader-title" };
  if (state.pairingUri) return { kind: "pairing", titleId: "pairing-title", uri: state.pairingUri };
  if (state.scanResult?.kind === "text") {
    return { kind: "text", titleId: "text-result-title", text: state.scanResult.text };
  }
  if (state.scanResult) return { kind: "link", titleId: "link-result-title", result: state.scanResult.result };
  return { kind: "home", titleId: "page-title" };
}

export type PairingGuideStatus = "checking" | "available" | "missing" | "unavailable";

export function pairingGuideStatus(store: { ready: boolean; error: boolean; hasPair: boolean }): PairingGuideStatus {
  if (!store.ready) return "checking";
  if (store.error) return "unavailable";
  return store.hasPair ? "available" : "missing";
}
