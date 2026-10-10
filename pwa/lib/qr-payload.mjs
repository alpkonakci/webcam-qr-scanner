import { MAX_QR_TEXT_LENGTH, parseWebUrl } from "./url-policy.mjs";

// Text is displayed, never interpreted as HTML, navigated to or relayed.
export function parseQrPayload(value) {
  const link = parseWebUrl(value);
  if (link.ok) return { kind: "link", result: link };
  if (typeof value !== "string" || !value.trim()) return { kind: "link", result: link };
  if (value.length > MAX_QR_TEXT_LENGTH) {
    return { kind: "link", result: { ok: false, reason: "The QR text is too long to display safely." } };
  }
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value)) {
    return { kind: "link", result: { ok: false, reason: "The QR contains unsupported control characters." } };
  }
  // A broken/unsafe address must not acquire link actions via the text path.
  if (/^(?:https?|javascript|vbscript|data|file):/i.test(value.trim())) {
    return { kind: "link", result: link };
  }
  return { kind: "text", text: value };
}
