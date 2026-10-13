export const MAX_QR_TEXT_LENGTH = 4096;

const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/;

export function parseWebUrl(value) {
  if (typeof value !== "string") {
    return { ok: false, reason: "The QR code does not contain text." };
  }

  const cleanValue = value.trim();
  if (!cleanValue) {
    return { ok: false, reason: "The QR code is empty." };
  }
  if (cleanValue.length > MAX_QR_TEXT_LENGTH) {
    return { ok: false, reason: "The QR code contains an unusually long address." };
  }
  if (CONTROL_CHARACTERS.test(cleanValue)) {
    return { ok: false, reason: "The QR code contains unsupported control characters." };
  }

  let parsed;
  try {
    parsed = new URL(cleanValue);
  } catch {
    return { ok: false, reason: "This QR code does not contain a valid web address." };
  }

  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    return { ok: false, reason: "Only HTTP and HTTPS web addresses are supported." };
  }
  if (!parsed.hostname) {
    return { ok: false, reason: "The web address does not contain a hostname." };
  }
  if (parsed.username || parsed.password) {
    return { ok: false, reason: "Web addresses containing embedded credentials are blocked." };
  }

  return {
    ok: true,
    href: parsed.href,
    hostname: parsed.hostname,
    insecure: parsed.protocol === "http:",
  };
}
