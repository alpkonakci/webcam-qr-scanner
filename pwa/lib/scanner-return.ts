/** A short-lived, same-origin acknowledgement; not a pairing credential. */
export interface ScannerReturn {
  pairingId: string;
  token: string;
  expiresAt: number;
}

function base64url(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes)).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

export function parseScannerReturn(hash: string, now = Math.floor(Date.now() / 1000)): ScannerReturn | null {
  const match = /^#open=([A-Za-z0-9_-]{71})$/.exec(hash);
  if (!match) return null;
  try {
    const bytes = Uint8Array.from(atob(match[1].replaceAll("-", "+").replaceAll("_", "/") + "="), (c) => c.charCodeAt(0));
    if (bytes.length !== 53 || bytes[0] !== 1 || base64url(bytes) !== match[1]) return null;
    const expiresAt = new DataView(bytes.buffer).getUint32(49);
    if (expiresAt <= now || expiresAt > now + 120) return null;
    return { pairingId: base64url(bytes.slice(1, 17)), token: base64url(bytes.slice(17, 49)), expiresAt };
  } catch { return null; }
}

export async function acknowledgeScannerReturn(
  value: ScannerReturn, signal?: AbortSignal,
): Promise<void> {
  // Relative URL only: an untrusted QR cannot send credentials to another host.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if (signal?.aborted || value.expiresAt <= Math.floor(Date.now() / 1000)) return;
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    const timeout = setTimeout(abort, 5000);
    try {
      const response = await fetch(`/v1/pairings/${value.pairingId}/opened`, {
        method: "POST", headers: { Authorization: `Bearer ${value.token}` },
        credentials: "same-origin", referrerPolicy: "no-referrer", cache: "no-store", signal: controller.signal,
      });
      if (response.status === 202 || response.status === 404 || response.status === 410) return;
      if (response.status !== 429 && response.status < 500) return;
    } catch { if (signal?.aborted) return; }
    finally {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", abort);
    }
  }
}
