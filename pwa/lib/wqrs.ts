export const WQRS_PROTOCOL = "wqrs/1";
const KEY_EPOCH = 1;
const PAIRING_TTL_SECONDS = 120;
const MESSAGE_TTL_SECONDS = 300;
const ACK_TTL_SECONDS = 10;
const MAX_CLOCK_SKEW_SECONDS = 120;

const PAIRING_QUERY_FIELDS = new Set([
  "v",
  "relay",
  "device",
  "pairing",
  "pairing_token",
  "pc_key",
  "secret",
  "expires",
]);

const PAIRING_ENVELOPE_FIELDS = new Set([
  "protocol",
  "device_id",
  "pairing_id",
  "phone_public_key",
  "expires_at",
  "type",
  "created_at",
  "nonce",
  "ciphertext",
]);

const MESSAGE_ENVELOPE_FIELDS = new Set([
  "protocol",
  "type",
  "pair_id",
  "key_epoch",
  "message_id",
  "created_at",
  "expires_at",
  "nonce",
  "ciphertext",
]);

export class WqrsError extends Error {}

export interface PairingQrData {
  relayOrigin: string;
  deviceId: string;
  pairingId: string;
  pairingToken: string;
  pcPublicKey: Uint8Array;
  pairingSecret: Uint8Array;
  expiresAt: number;
}

export interface PairingAttempt {
  qr: PairingQrData;
  phonePublicKey: Uint8Array;
  handshakeKey: CryptoKey;
  rootKey: CryptoKey;
  requestEnvelope: Record<string, unknown>;
}

export interface SenderCredentials {
  relayOrigin: string;
  pairId: string;
  senderToken: string;
  rootKey: CryptoKey;
  pcLabel: string;
  keyEpoch: number;
  pairedAt: number;
}

export interface BuiltUrlMessage {
  messageId: string;
  envelope: Record<string, unknown>;
}

export function isPairingUri(value: string): boolean {
  return value.startsWith("wqrs://pair?");
}

export function parsePairingUri(value: string, now = unixTime()): PairingQrData {
  if (!value || value !== value.trim()) fail("Pairing code is malformed.");
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    fail("Pairing code is malformed.");
  }
  if (
    parsed.protocol !== "wqrs:" ||
    parsed.hostname !== "pair" ||
    (parsed.pathname !== "" && parsed.pathname !== "/") ||
    parsed.hash !== ""
  ) {
    fail("Pairing code target is invalid.");
  }
  const entries = [...parsed.searchParams.entries()];
  if (
    entries.length !== PAIRING_QUERY_FIELDS.size ||
    entries.some(([key]) => !PAIRING_QUERY_FIELDS.has(key)) ||
    new Set(entries.map(([key]) => key)).size !== entries.length
  ) {
    fail("Pairing code fields are invalid.");
  }
  const field = (name: string): string => {
    const result = parsed.searchParams.get(name);
    if (result === null) fail("Pairing code is incomplete.");
    return result;
  };
  if (field("v") !== "1") fail("Pairing code version is unsupported.");
  const expiresText = field("expires");
  if (!/^(0|[1-9][0-9]*)$/.test(expiresText)) fail("Pairing expiry is invalid.");
  const expiresAt = Number(expiresText);
  if (!Number.isSafeInteger(expiresAt)) fail("Pairing expiry is invalid.");
  if (expiresAt < now) fail("This pairing code has expired.");
  if (expiresAt - now > PAIRING_TTL_SECONDS + MAX_CLOCK_SKEW_SECONDS) {
    fail("Pairing code lifetime is invalid.");
  }
  const pcPublicKey = decodeBase64Url(field("pc_key"), 65, "PC public key");
  if (pcPublicKey[0] !== 4) fail("PC public key is invalid.");
  return {
    relayOrigin: normalizeRelayOrigin(field("relay")),
    deviceId: checkedBase64Url(field("device"), 16, "device ID"),
    pairingId: checkedBase64Url(field("pairing"), 16, "pairing ID"),
    pairingToken: checkedBase64Url(field("pairing_token"), 32, "pairing token"),
    pcPublicKey,
    pairingSecret: decodeBase64Url(field("secret"), 32, "pairing secret"),
    expiresAt,
  };
}

export async function createPhonePairingAttempt(
  pairingUri: string,
  phoneLabel: string,
  now = unixTime(),
): Promise<PairingAttempt> {
  requireWebCrypto();
  const qr = parsePairingUri(pairingUri, now);
  const cleanPhoneLabel = validateLabel(phoneLabel, "Phone name");
  const keyPair = (await crypto.subtle.generateKey(
    { name: "ECDH", namedCurve: "P-256" },
    false,
    ["deriveBits"],
  )) as CryptoKeyPair;
  const phonePublicKey = new Uint8Array(
    await crypto.subtle.exportKey("raw", keyPair.publicKey),
  );
  const pcPublicKey = await crypto.subtle.importKey(
    "raw",
    bytesBuffer(qr.pcPublicKey),
    { name: "ECDH", namedCurve: "P-256" },
    false,
    [],
  );
  const sharedSecret = new Uint8Array(
    await crypto.subtle.deriveBits(
      { name: "ECDH", public: pcPublicKey },
      keyPair.privateKey,
      256,
    ),
  );
  const transcript = {
    protocol: WQRS_PROTOCOL,
    relay_origin: qr.relayOrigin,
    device_id: qr.deviceId,
    pairing_id: qr.pairingId,
    expires_at: qr.expiresAt,
    pc_public_key: encodeBase64Url(qr.pcPublicKey),
    phone_public_key: encodeBase64Url(phonePublicKey),
  };
  const transcriptHash = new Uint8Array(
    await crypto.subtle.digest("SHA-256", bytesBuffer(encodeUtf8(canonicalJson(transcript)))),
  );
  const handshakeBytes = await hkdf(
    sharedSecret,
    qr.pairingSecret,
    concatenate(encodeUtf8("wqrs/handshake/v1"), transcriptHash),
  );
  const rootBytes = await hkdf(
    sharedSecret,
    qr.pairingSecret,
    concatenate(encodeUtf8("wqrs/root/v1"), transcriptHash),
  );
  const handshakeKey = await crypto.subtle.importKey(
    "raw",
    bytesBuffer(handshakeBytes),
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
  const rootKey = await crypto.subtle.importKey(
    "raw",
    bytesBuffer(rootBytes),
    "HKDF",
    false,
    ["deriveKey"],
  );
  const requestEnvelope = await buildPairingEnvelope(
    qr,
    phonePublicKey,
    "pair_request",
    handshakeKey,
    {
      payload_version: 1,
      kind: "pair_request",
      phone_label: cleanPhoneLabel,
      platform: "pwa",
    },
    now,
  );
  return { qr, phonePublicKey, handshakeKey, rootKey, requestEnvelope };
}

export async function decryptPairingResult(
  attempt: PairingAttempt,
  value: unknown,
  now = unixTime(),
): Promise<SenderCredentials | null> {
  const envelope = validatePairingEnvelope(value, attempt, "pair_result", now);
  const payload = await decryptPayload(envelope, attempt.handshakeKey);
  if (canonicalJson(payload) === canonicalJson({ payload_version: 1, kind: "pair_rejected" })) {
    return null;
  }
  requireExactFields(payload, [
    "payload_version",
    "kind",
    "pair_id",
    "sender_token",
    "pc_label",
    "key_epoch",
  ]);
  if (payload.payload_version !== 1 || payload.kind !== "pair_approved" || payload.key_epoch !== 1) {
    fail("Pairing result is unsupported.");
  }
  return {
    relayOrigin: attempt.qr.relayOrigin,
    pairId: checkedBase64Url(payload.pair_id, 16, "pair ID"),
    senderToken: checkedBase64Url(payload.sender_token, 32, "sender token"),
    rootKey: attempt.rootKey,
    pcLabel: validateLabel(payload.pc_label, "PC name"),
    keyEpoch: KEY_EPOCH,
    pairedAt: now,
  };
}

export async function buildUrlEnvelope(
  credentials: SenderCredentials,
  url: string,
  now = unixTime(),
): Promise<BuiltUrlMessage> {
  validateWebUrl(url);
  const messageId = randomBase64Url(16);
  const messageIdBytes = decodeBase64Url(messageId, 16, "message ID");
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveMessageKey(credentials.rootKey, messageIdBytes, "wqrs/message-key/v1", ["encrypt"]);
  const aad = {
    protocol: WQRS_PROTOCOL,
    type: "url_message",
    pair_id: credentials.pairId,
    key_epoch: credentials.keyEpoch,
    message_id: messageId,
    created_at: now,
    expires_at: now + MESSAGE_TTL_SECONDS,
    nonce: encodeBase64Url(nonce),
  };
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: bytesBuffer(nonce), additionalData: bytesBuffer(encodeUtf8(canonicalJson(aad))), tagLength: 128 },
    key,
    bytesBuffer(encodeUtf8(canonicalJson({ payload_version: 1, kind: "url", url }))),
  );
  return {
    messageId,
    envelope: { ...aad, ciphertext: encodeBase64Url(new Uint8Array(ciphertext)) },
  };
}

export async function verifyDeliveryAck(
  credentials: SenderCredentials,
  expectedMessageId: string,
  value: unknown,
  now = unixTime(),
): Promise<void> {
  const envelope = validateMessageEnvelope(value, credentials, "delivered_ack", ACK_TTL_SECONDS, now);
  if (envelope.message_id !== expectedMessageId) fail("Delivery receipt belongs to another message.");
  const messageId = decodeBase64Url(expectedMessageId, 16, "message ID");
  const key = await deriveMessageKey(credentials.rootKey, messageId, "wqrs/ack-key/v1", ["decrypt"]);
  const payload = await decryptPayload(envelope, key);
  requireExactFields(payload, ["payload_version", "kind", "message_id"]);
  if (
    payload.payload_version !== 1 ||
    payload.kind !== "delivered" ||
    payload.message_id !== expectedMessageId
  ) {
    fail("Delivery receipt is invalid.");
  }
}

async function buildPairingEnvelope(
  qr: PairingQrData,
  phonePublicKey: Uint8Array,
  type: "pair_request" | "pair_result",
  key: CryptoKey,
  payload: Record<string, unknown>,
  now: number,
): Promise<Record<string, unknown>> {
  if (now > qr.expiresAt) fail("This pairing code has expired.");
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const aad = {
    protocol: WQRS_PROTOCOL,
    device_id: qr.deviceId,
    pairing_id: qr.pairingId,
    phone_public_key: encodeBase64Url(phonePublicKey),
    expires_at: qr.expiresAt,
    type,
    created_at: now,
    nonce: encodeBase64Url(nonce),
  };
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: bytesBuffer(nonce), additionalData: bytesBuffer(encodeUtf8(canonicalJson(aad))), tagLength: 128 },
    key,
    bytesBuffer(encodeUtf8(canonicalJson(payload))),
  );
  return { ...aad, ciphertext: encodeBase64Url(new Uint8Array(ciphertext)) };
}

function validatePairingEnvelope(
  value: unknown,
  attempt: PairingAttempt,
  expectedType: "pair_result",
  now: number,
): Record<string, unknown> {
  const envelope = requireObject(value, "Pairing result is invalid.");
  requireFieldSet(envelope, PAIRING_ENVELOPE_FIELDS);
  if (
    envelope.protocol !== WQRS_PROTOCOL ||
    envelope.type !== expectedType ||
    envelope.device_id !== attempt.qr.deviceId ||
    envelope.pairing_id !== attempt.qr.pairingId ||
    envelope.phone_public_key !== encodeBase64Url(attempt.phonePublicKey) ||
    envelope.expires_at !== attempt.qr.expiresAt ||
    !isSafeTimestamp(envelope.created_at) ||
    envelope.created_at > now + MAX_CLOCK_SKEW_SECONDS ||
    envelope.created_at > attempt.qr.expiresAt ||
    attempt.qr.expiresAt < now
  ) {
    fail("Pairing result does not match this phone or pairing session.");
  }
  decodeBase64Url(envelope.nonce, 12, "pairing nonce");
  decodeBase64Url(envelope.ciphertext, undefined, "pairing ciphertext", 16);
  return envelope;
}

function validateMessageEnvelope(
  value: unknown,
  credentials: SenderCredentials,
  expectedType: "delivered_ack",
  maximumTtl: number,
  now: number,
): Record<string, unknown> {
  const envelope = requireObject(value, "Delivery receipt is invalid.");
  requireFieldSet(envelope, MESSAGE_ENVELOPE_FIELDS);
  if (
    envelope.protocol !== WQRS_PROTOCOL ||
    envelope.type !== expectedType ||
    envelope.pair_id !== credentials.pairId ||
    envelope.key_epoch !== credentials.keyEpoch ||
    !isSafeTimestamp(envelope.created_at) ||
    !isSafeTimestamp(envelope.expires_at) ||
    envelope.expires_at < envelope.created_at ||
    envelope.expires_at - envelope.created_at > maximumTtl ||
    envelope.created_at > now + MAX_CLOCK_SKEW_SECONDS ||
    envelope.expires_at < now
  ) {
    fail("Delivery receipt is expired or belongs to another pairing.");
  }
  checkedBase64Url(envelope.pair_id, 16, "pair ID");
  checkedBase64Url(envelope.message_id, 16, "message ID");
  decodeBase64Url(envelope.nonce, 12, "delivery nonce");
  decodeBase64Url(envelope.ciphertext, undefined, "delivery ciphertext", 16);
  return envelope;
}

async function decryptPayload(
  envelope: Record<string, unknown>,
  key: CryptoKey,
): Promise<Record<string, unknown>> {
  const aad = Object.fromEntries(Object.entries(envelope).filter(([name]) => name !== "ciphertext"));
  let plaintext: ArrayBuffer;
  try {
    plaintext = await crypto.subtle.decrypt(
      {
        name: "AES-GCM",
        iv: bytesBuffer(decodeBase64Url(envelope.nonce, 12, "nonce")),
        additionalData: bytesBuffer(encodeUtf8(canonicalJson(aad))),
        tagLength: 128,
      },
      key,
      bytesBuffer(decodeBase64Url(envelope.ciphertext, undefined, "ciphertext", 16)),
    );
  } catch {
    fail("Encrypted message authentication failed.");
  }
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(plaintext);
  } catch {
    fail("Encrypted message is not valid UTF-8.");
  }
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch {
    fail("Encrypted message is not valid JSON.");
  }
  const result = requireObject(payload, "Encrypted payload is invalid.");
  if (canonicalJson(result) !== text) fail("Encrypted payload is not canonical JSON.");
  return result;
}

async function hkdf(ikm: Uint8Array, salt: Uint8Array, info: Uint8Array): Promise<Uint8Array> {
  const material = await crypto.subtle.importKey("raw", bytesBuffer(ikm), "HKDF", false, ["deriveBits"]);
  return new Uint8Array(
    await crypto.subtle.deriveBits(
      { name: "HKDF", hash: "SHA-256", salt: bytesBuffer(salt), info: bytesBuffer(info) },
      material,
      256,
    ),
  );
}

async function deriveMessageKey(
  rootKey: CryptoKey,
  salt: Uint8Array,
  info: string,
  usages: KeyUsage[],
): Promise<CryptoKey> {
  return crypto.subtle.deriveKey(
    { name: "HKDF", hash: "SHA-256", salt: bytesBuffer(salt), info: bytesBuffer(encodeUtf8(info)) },
    rootKey,
    { name: "AES-GCM", length: 256 },
    false,
    usages,
  );
}

function normalizeRelayOrigin(value: string): string {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    fail("Relay address is invalid.");
  }
  const hostname = parsed.hostname.toLowerCase();
  const loopback = hostname === "127.0.0.1" || hostname === "::1" || hostname === "localhost";
  if ((parsed.protocol !== "https:" && !(parsed.protocol === "http:" && loopback)) || !hostname) {
    fail("Relay must use HTTPS.");
  }
  if (parsed.username || parsed.password || (parsed.pathname !== "" && parsed.pathname !== "/") || parsed.search || parsed.hash) {
    fail("Relay address must be an origin without a path.");
  }
  return parsed.origin;
}

function validateWebUrl(value: string): void {
  if (!value || value !== value.trim() || new TextEncoder().encode(value).length > 4096) {
    fail("Web address is invalid.");
  }
  if ([...value].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127) || value.includes("\\")) {
    fail("Web address contains unsafe characters.");
  }
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    fail("Web address is invalid.");
  }
  if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname || parsed.username || parsed.password) {
    fail("Only absolute HTTP or HTTPS addresses are accepted.");
  }
}

function validateLabel(value: unknown, field: string): string {
  if (
    typeof value !== "string" ||
    !value ||
    value !== value.trim() ||
    value.length > 80 ||
    [...value].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)
  ) {
    fail(`${field} is invalid.`);
  }
  return value;
}

export function canonicalJson(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || value < 0) fail("Protocol JSON integer is invalid.");
    return String(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const object = requireObject(value, "Protocol JSON value is unsupported.");
  const keys = Object.keys(object);
  if (keys.some((key) => !/^[\x00-\x7f]+$/.test(key))) fail("Protocol property is not ASCII.");
  return `{${keys.sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(object[key])}`).join(",")}}`;
}

export function encodeBase64Url(value: Uint8Array): string {
  let binary = "";
  for (const byte of value) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

export function decodeBase64Url(
  value: unknown,
  expectedBytes: number | undefined,
  field: string,
  minimumBytes?: number,
): Uint8Array {
  if (typeof value !== "string" || !/^[A-Za-z0-9_-]+$/.test(value) || value.includes("=")) {
    fail(`${field} is invalid.`);
  }
  let binary: string;
  try {
    const base64 = value.replaceAll("-", "+").replaceAll("_", "/");
    binary = atob(base64 + "=".repeat((4 - (base64.length % 4)) % 4));
  } catch {
    fail(`${field} is invalid.`);
  }
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  if (expectedBytes !== undefined && bytes.length !== expectedBytes) fail(`${field} has the wrong size.`);
  if (minimumBytes !== undefined && bytes.length < minimumBytes) fail(`${field} is too short.`);
  if (encodeBase64Url(bytes) !== value) fail(`${field} is not canonical.`);
  return bytes;
}

function checkedBase64Url(value: unknown, bytes: number, field: string): string {
  decodeBase64Url(value, bytes, field);
  return value as string;
}

function requireObject(value: unknown, message: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail(message);
  return value as Record<string, unknown>;
}

function requireExactFields(value: Record<string, unknown>, fields: string[]): void {
  requireFieldSet(value, new Set(fields));
}

function requireFieldSet(value: Record<string, unknown>, fields: Set<string>): void {
  const keys = Object.keys(value);
  if (keys.length !== fields.size || keys.some((key) => !fields.has(key))) fail("Protocol fields are invalid.");
}

function isSafeTimestamp(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function randomBase64Url(bytes: number): string {
  return encodeBase64Url(crypto.getRandomValues(new Uint8Array(bytes)));
}

function encodeUtf8(value: string): Uint8Array {
  return new TextEncoder().encode(value);
}

function bytesBuffer(value: Uint8Array): ArrayBuffer {
  return Uint8Array.from(value).buffer;
}

function concatenate(...values: Uint8Array[]): Uint8Array {
  const result = new Uint8Array(values.reduce((total, value) => total + value.length, 0));
  let offset = 0;
  for (const value of values) {
    result.set(value, offset);
    offset += value.length;
  }
  return result;
}

function requireWebCrypto(): void {
  if (!globalThis.crypto?.subtle) fail("This browser does not support the required WebCrypto APIs.");
}

function unixTime(): number {
  return Math.floor(Date.now() / 1000);
}

function fail(message: string): never {
  throw new WqrsError(message);
}
