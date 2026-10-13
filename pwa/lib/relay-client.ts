import { removePair, savePair } from "./pair-store.ts";
import {
  buildUrlEnvelope,
  createPhonePairingAttempt,
  decryptPairingResult,
  parsePairingUri,
  verifyDeliveryAck,
  type SenderCredentials,
} from "./wqrs.ts";

const POLL_INTERVAL_MS = 500;
const DELIVERY_WAIT_MS = 15_000;
const RECEIPT_WATCH_INTERVAL_MS = 1_500;
const RECEIPT_REQUEST_TIMEOUT_MS = 8_000;

interface DeliveryAttempt {
  messageId: string;
  expiresAt: number;
  deliveryId: string | null;
  submitted: boolean;
  verified: boolean;
  inFlight?: Promise<void>;
  envelope: Record<string, unknown>;
}

// Page-memory only: no URL, token or delivery data is written to browser storage.
// The same link reuses its attempt unless an explicit new scan retires a verified
// delivery. Uncertain attempts stay locked instead of POSTing twice.
const deliveryAttempts = new Map<string, Promise<DeliveryAttempt>>();

export class PendingDeliveryError extends Error {
  readonly code = "delivery_pending";

  constructor() {
    super("Delivery is not confirmed yet. This link may still arrive. Keep this page open and check its status before sending again.");
  }
}

export class RelayClientError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

export function isPairRevokedError(error: unknown): error is RelayClientError {
  return error instanceof RelayClientError && error.code === "pair_revoked";
}

export async function removePairIfRevoked(
  error: unknown,
  pairId: string,
  removeStoredPair: (storedPairId: string) => Promise<void> = removePair,
): Promise<boolean> {
  if (!isPairRevokedError(error)) return false;
  await removeStoredPair(pairId);
  return true;
}

export async function checkStoredPair(
  credentials: SenderCredentials,
  options: {
    signal?: AbortSignal;
    removeStoredPair?: (pairId: string) => Promise<void>;
  } = {},
): Promise<"active" | "revoked"> {
  try {
    const response = await relayFetch(
      `${credentials.relayOrigin}/v1/pairs/${credentials.pairId}`,
      credentials.senderToken,
      { method: "GET", expectedStatus: 200, signal: options.signal },
    );
    if (response.body.status !== "active" || response.body.pair_id !== credentials.pairId) {
      throw new RelayClientError("invalid_relay_response", "The relay returned an invalid response.");
    }
    return "active";
  } catch (error) {
    if (
      error instanceof RelayClientError &&
      (error.code === "pair_revoked" || error.code === "unauthorized")
    ) {
      await (options.removeStoredPair ?? removePair)(credentials.pairId);
      return "revoked";
    }
    throw error;
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
    await abortableDelay(POLL_INTERVAL_MS, signal);
  }
  throw new RelayClientError("pairing_expired", "The pairing code expired. Create a new code on the PC.");
}

export async function notifyPairingOpened(
  pairingUri: string,
  signal?: AbortSignal,
): Promise<void> {
  const qr = parsePairingTransport(pairingUri);
  await relayFetch(
    `${qr.relayOrigin}/v1/pairings/${qr.pairingId}/opened`,
    qr.pairingToken,
    { method: "POST", expectedStatus: 202, signal },
  );
}

export async function cancelPairingFromPhone(
  pairingUri: string,
): Promise<void> {
  const qr = parsePairingTransport(pairingUri);
  await relayFetch(
    `${qr.relayOrigin}/v1/pairings/${qr.pairingId}/phone-cancel`,
    qr.pairingToken,
    { method: "POST", expectedStatus: 202 },
  );
}

export async function sendUrlToPc(
  credentials: SenderCredentials,
  url: string,
  signal?: AbortSignal,
): Promise<void> {
  const key = deliveryAttemptKey(credentials, url);
  for (const [storedKey, stored] of deliveryAttempts) {
    try {
      const attempt = await stored;
      if (attempt.expiresAt < Math.floor(Date.now() / 1000)) deliveryAttempts.delete(storedKey);
    } catch {
      deliveryAttempts.delete(storedKey);
    }
  }
  let stored = deliveryAttempts.get(key);
  if (!stored) {
    stored = buildUrlEnvelope(credentials, url).then((message) => ({
      messageId: message.messageId,
      expiresAt: message.envelope.expires_at as number,
      deliveryId: null,
      submitted: false,
      verified: false,
      envelope: message.envelope,
    }));
    deliveryAttempts.set(key, stored);
  }
  let attempt: DeliveryAttempt;
  try {
    attempt = await stored;
  } catch (error) {
    deliveryAttempts.delete(key);
    throw error;
  }
  if (attempt.verified) return;
  if (attempt.inFlight) return attempt.inFlight;
  attempt.inFlight = submitOrCheckDelivery(credentials, attempt, signal).catch((error) => {
    // Explicit rejection before enqueueing is safe to retry. A lost response is
    // not proof that the POST failed, so uncertain attempts remain locked.
    if ((!attempt.deliveryId && isDefiniteSubmissionRejection(error)) || isTerminalDeliveryError(error)) {
      deliveryAttempts.delete(key);
    }
    throw error;
  }).finally(() => { attempt.inFlight = undefined; });
  return attempt.inFlight;
}

export async function prepareUrlRescan(
  credentials: SenderCredentials,
  url: string,
): Promise<boolean> {
  // Only an explicit new scan may retire a verified attempt. Pending or lost
  // receipts must keep their original message ID, even when the QR is rescanned.
  const key = deliveryAttemptKey(credentials, url);
  const stored = deliveryAttempts.get(key);
  if (!stored) return false;
  let attempt: DeliveryAttempt;
  try { attempt = await stored; } catch { return false; }
  if (!attempt.verified || attempt.inFlight || deliveryAttempts.get(key) !== stored) return false;
  deliveryAttempts.delete(key);
  return true;
}

export async function checkUrlDelivery(
  credentials: SenderCredentials,
  url: string,
  signal?: AbortSignal,
): Promise<void> {
  const stored = deliveryAttempts.get(deliveryAttemptKey(credentials, url));
  if (!stored) throw new RelayClientError("delivery_expired", "The delivery window ended. Check your PC before sending again.");
  const attempt = await stored;
  if (attempt.verified) return;
  if (attempt.inFlight) return attempt.inFlight;
  attempt.inFlight = readDeliveryReceipt(credentials, attempt, signal)
    .catch((error) => {
      if (isTerminalDeliveryError(error)) deliveryAttempts.delete(deliveryAttemptKey(credentials, url));
      throw error;
    })
    .finally(() => { attempt.inFlight = undefined; });
  return attempt.inFlight;
}

export async function watchUrlDelivery(
  credentials: SenderCredentials,
  url: string,
  signal?: AbortSignal,
): Promise<void> {
  // GET-only, bounded by the existing attempt's authenticated URL expiry.
  // No new message, persistent URL history or browser-background guarantee.
  while (true) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    try {
      await checkUrlDelivery(credentials, url, signal);
      return;
    } catch (error) {
      if (!(error instanceof PendingDeliveryError)) throw error;
    }
    await abortableDelay(RECEIPT_WATCH_INTERVAL_MS, signal);
  }
}

function deliveryAttemptKey(credentials: SenderCredentials, url: string): string {
  return JSON.stringify([credentials.relayOrigin, credentials.pairId, url]);
}

function isDefiniteSubmissionRejection(error: unknown): boolean {
  return error instanceof RelayClientError && [
    "receiver_offline", "pair_revoked", "unauthorized", "rate_limited",
    "invalid_request", "invalid_envelope", "message_expired",
  ].includes(error.code);
}

function isTerminalDeliveryError(error: unknown): boolean {
  return error instanceof RelayClientError && ["delivery_expired", "delivery_rejected"].includes(error.code);
}

async function submitOrCheckDelivery(
  credentials: SenderCredentials,
  attempt: DeliveryAttempt,
  signal?: AbortSignal,
): Promise<void> {
  if (attempt.submitted) return readDeliveryReceipt(credentials, attempt, signal);
  attempt.submitted = true;
  try {
    const accepted = await relayFetch(
      `${credentials.relayOrigin}/v1/pairs/${credentials.pairId}/messages`,
      credentials.senderToken,
      { method: "POST", body: attempt.envelope, expectedStatus: 202, signal },
    );
    attempt.deliveryId = stringField(accepted.body, "delivery_id");
    if (!attempt.deliveryId) throw new PendingDeliveryError();
  } catch (error) {
    if (isDefiniteSubmissionRejection(error)) throw error;
    throw new PendingDeliveryError();
  }
  const deadline = Date.now() + DELIVERY_WAIT_MS;
  while (Date.now() < deadline) {
    try {
      await readDeliveryReceipt(credentials, attempt, signal);
      return;
    } catch (error) {
      if (!(error instanceof PendingDeliveryError)) throw error;
    }
    await abortableDelay(350, signal);
  }
  throw new PendingDeliveryError();
}

async function readDeliveryReceipt(
  credentials: SenderCredentials,
  attempt: DeliveryAttempt,
  signal?: AbortSignal,
): Promise<void> {
  if (attempt.expiresAt < Math.floor(Date.now() / 1000)) {
    throw new RelayClientError("delivery_expired", "The delivery window ended. Check your PC before sending again.");
  }
  if (!attempt.deliveryId) throw new PendingDeliveryError();
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  if (signal?.aborted) onAbort();
  else signal?.addEventListener("abort", onAbort, { once: true });
  const timeout = setTimeout(() => controller.abort(), RECEIPT_REQUEST_TIMEOUT_MS);
  try {
    const response = await relayFetch(
      `${credentials.relayOrigin}/v1/pairs/${credentials.pairId}/deliveries/${attempt.deliveryId}`,
      credentials.senderToken,
      { method: "GET", expectedStatus: [200, 202], signal: controller.signal },
    );
    if (response.status === 200) {
      await verifyDeliveryAck(credentials, attempt.messageId, objectField(response.body, "envelope"));
      attempt.verified = true;
      return;
    }
  } catch (error) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (error instanceof RelayClientError && [
      "pair_revoked", "unauthorized", "delivery_rejected", "delivery_expired", "delivery_receipt_expired",
    ].includes(error.code)) throw error;
    // A failed status request or invalid receipt must not permit a duplicate POST
    // or be presented as verified delivery.
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", onAbort);
  }
  throw new PendingDeliveryError();
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
      credentials: "same-origin",
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
    case "pair_revoked":
      return "Access to this PC was removed. Pair this phone with a PC again.";
    case "unauthorized":
      return "This pairing is no longer valid. Pair the phone again.";
    case "pairing_expired":
      return "The pairing code expired. Create a new code on the PC.";
    case "rate_limited":
      return "Too many requests were made. Wait briefly and try again.";
    case "delivery_rejected":
      return "The PC rejected the encrypted delivery.";
    case "delivery_expired":
      return "The delivery window ended. Check your PC before sending again.";
    case "delivery_receipt_expired":
      return "The receipt is no longer available. The link may already be on your PC. Check your PC before sending again.";
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

function parsePairingTransport(pairingUri: string): {
  relayOrigin: string;
  pairingId: string;
  pairingToken: string;
} {
  const qr = parsePairingUri(pairingUri);
  return {
    relayOrigin: qr.relayOrigin,
    pairingId: qr.pairingId,
    pairingToken: qr.pairingToken,
  };
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

export function abortableDelay(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const onAbort = () => {
      clearTimeout(timeout);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timeout = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, milliseconds);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}
