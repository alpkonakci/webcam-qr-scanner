import { savePair } from "./pair-store";
import {
  buildUrlEnvelope,
  createPhonePairingAttempt,
  decryptPairingResult,
  verifyDeliveryAck,
  type SenderCredentials,
} from "./wqrs";

const POLL_INTERVAL_MS = 500;

export class RelayClientError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

export async function pairWithPc(
  pairingUri: string,
  phoneLabel: string,
  signal?: AbortSignal,
): Promise<SenderCredentials> {
  const attempt = await createPhonePairingAttempt(pairingUri, phoneLabel);
  await relayFetch(
    `${attempt.qr.relayOrigin}/v1/pairings/${attempt.qr.pairingId}/request`,
    attempt.qr.pairingToken,
    { method: "POST", body: attempt.requestEnvelope, expectedStatus: 202, signal },
  );
  while (Math.floor(Date.now() / 1000) <= attempt.qr.expiresAt) {
    const response = await relayFetch(
      `${attempt.qr.relayOrigin}/v1/pairings/${attempt.qr.pairingId}/result`,
      attempt.qr.pairingToken,
      { method: "GET", expectedStatus: [200, 202], signal },
    );
    if (response.status === 200) {
      const envelope = objectField(response.body, "envelope");
      const credentials = await decryptPairingResult(attempt, envelope);
      if (credentials === null) {
        throw new RelayClientError("pairing_rejected", "Pairing was rejected on the PC.");
      }
      try {
        await savePair(credentials);
      } catch {
        throw new RelayClientError(
          "secure_storage_unavailable",
          "The browser could not securely save this pairing. Nothing was stored.",
        );
      }
      return credentials;
    }
    await delay(POLL_INTERVAL_MS, signal);
  }
  throw new RelayClientError("pairing_expired", "The pairing code expired. Create a new code on the PC.");
}

export async function sendUrlToPc(
  credentials: SenderCredentials,
  url: string,
  signal?: AbortSignal,
): Promise<void> {
  const message = await buildUrlEnvelope(credentials, url);
  const accepted = await relayFetch(
    `${credentials.relayOrigin}/v1/pairs/${credentials.pairId}/messages`,
    credentials.senderToken,
    { method: "POST", body: message.envelope, expectedStatus: 202, signal },
  );
  const deliveryId = stringField(accepted.body, "delivery_id");
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    const response = await relayFetch(
      `${credentials.relayOrigin}/v1/pairs/${credentials.pairId}/deliveries/${deliveryId}`,
      credentials.senderToken,
      { method: "GET", expectedStatus: [200, 202], signal },
    );
    if (response.status === 200) {
      await verifyDeliveryAck(credentials, message.messageId, objectField(response.body, "envelope"));
      return;
    }
    await delay(350, signal);
  }
  throw new RelayClientError(
    "delivery_timeout",
    "The PC did not confirm receipt in time. The link was not reported as delivered.",
  );
}

interface RelayFetchOptions {
  method: "GET" | "POST";
  body?: Record<string, unknown>;
  expectedStatus: number | number[];
  signal?: AbortSignal;
}

async function relayFetch(
  url: string,
  token: string,
  options: RelayFetchOptions,
): Promise<{ status: number; body: Record<string, unknown> }> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      cache: "no-store",
      credentials: "omit",
      referrerPolicy: "no-referrer",
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new RelayClientError("relay_unreachable", "The encrypted relay could not be reached.");
  }
  let body: unknown = {};
  try {
    body = await response.json();
  } catch {
    // Invalid bodies are reported below without exposing server HTML.
  }
  const expected = Array.isArray(options.expectedStatus) ? options.expectedStatus : [options.expectedStatus];
  if (!expected.includes(response.status)) {
    const value = isObject(body) && isObject(body.error) ? body.error : null;
    const code = value && typeof value.code === "string" ? value.code : "invalid_relay_response";
    throw new RelayClientError(code, relayErrorMessage(code));
  }
  if (!isObject(body)) {
    throw new RelayClientError("invalid_relay_response", "The relay returned an invalid response.");
  }
  return { status: response.status, body };
}

function relayErrorMessage(code: string): string {
  switch (code) {
    case "receiver_offline":
      return "Your paired PC is offline or QR Scanner is not running.";
    case "unauthorized":
      return "This pairing is no longer valid. Pair the phone again.";
    case "pairing_expired":
      return "The pairing code expired. Create a new code on the PC.";
    case "rate_limited":
      return "Too many requests were made. Wait briefly and try again.";
    case "delivery_rejected":
      return "The PC rejected the encrypted delivery.";
    default:
      return "The relay rejected the request safely.";
  }
}

function objectField(value: Record<string, unknown>, name: string): Record<string, unknown> {
  const field = value[name];
  if (!isObject(field)) {
    throw new RelayClientError("invalid_relay_response", "The relay returned an invalid response.");
  }
  return field;
}

function stringField(value: Record<string, unknown>, name: string): string {
  const field = value[name];
  if (typeof field !== "string") {
    throw new RelayClientError("invalid_relay_response", "The relay returned an invalid response.");
  }
  return field;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function delay(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timeout = window.setTimeout(resolve, milliseconds);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timeout);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}
