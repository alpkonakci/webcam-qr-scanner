const PROTOCOL = "wqrs/1";
const PAIRING_TTL_SECONDS = 120;
const MESSAGE_TTL_SECONDS = 300;
const MAX_CLOCK_SKEW_SECONDS = 120;
const RECEIVER_ONLINE_SECONDS = 15;
const DELIVERY_LEASE_SECONDS = 8;
const MAX_REQUEST_BYTES = 12 * 1024;

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

interface RelayEnv {
  DB: D1Database;
}

interface RelayContext {
  waitUntil(promise: Promise<unknown>): void;
}

interface PairingRow {
  pairing_id: string;
  device_id: string;
  pairing_token_hash: string;
  expires_at: number;
  request_envelope: string | null;
  result_envelope: string | null;
  status: string;
}

interface PairRow {
  pair_id: string;
  device_id: string;
  sender_token_hash: string;
  revoked_at: number | null;
  receiver_token_hash?: string;
  last_seen_at?: number | null;
}

interface DeliveryRow {
  delivery_id: string;
  pair_id: string;
  device_id: string;
  message_id: string;
  envelope: string;
  expires_at: number;
  status: string;
  ack_envelope: string | null;
}

class RelayError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryAfterSeconds?: number;

  constructor(
    status: number,
    code: string,
    message: string,
    retryAfterSeconds?: number,
  ) {
    super(message);
    this.status = status;
    this.code = code;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export async function handleRelayRequest(
  request: Request,
  env: RelayEnv,
  ctx: RelayContext,
): Promise<Response | null> {
  const url = new URL(request.url);
  if (url.pathname !== "/healthz" && !url.pathname.startsWith("/v1/")) {
    return null;
  }

  try {
    if ((crypto.getRandomValues(new Uint8Array(1))[0] & 63) === 0) {
      ctx.waitUntil(cleanExpiredState(env.DB, unixTime()));
    }
    return await routeRelayRequest(request, url, env.DB);
  } catch (error) {
    if (error instanceof RelayError) {
      return relayError(error);
    }
    console.error("relay request failed", error);
    return relayError(
      new RelayError(500, "internal_error", "The relay could not process the request."),
    );
  }
}

async function routeRelayRequest(
  request: Request,
  url: URL,
  db: D1Database,
): Promise<Response> {
  const method = request.method.toUpperCase();
  const path = url.pathname;

  if (method === "GET" && path === "/healthz") {
    return json({ status: "ok", protocol: PROTOCOL });
  }
  if (method === "POST" && path === "/v1/devices") {
    return createDevice(request, db);
  }
  if (method === "POST" && path === "/v1/pairings") {
    return createPairing(request, db);
  }
  const pairingMatch = path.match(
    /^\/v1\/pairings\/([A-Za-z0-9_-]{22})(?:\/(request|result|opened|phone-cancel))?$/,
  );
  if (pairingMatch) {
    const [, pairingId, action] = pairingMatch;
    if (method === "DELETE" && action === undefined) {
      return cancelPairing(request, db, pairingId);
    }
    if (action === "request" && method === "POST") {
      return submitPairingRequest(request, db, pairingId);
    }
    if (action === "request" && method === "GET") {
      return getPairingRequest(request, db, pairingId);
    }
    if (action === "opened" && method === "POST") {
      return markPairingOpened(request, db, pairingId);
    }
    if (action === "phone-cancel" && method === "POST") {
      return cancelPairingFromPhone(request, db, pairingId);
    }
    if (action === "result" && method === "POST") {
      return submitPairingResult(request, db, pairingId);
    }
    if (action === "result" && method === "GET") {
      return getPairingResult(request, db, pairingId);
    }
  }
  if (method === "POST" && path === "/v1/pairs") {
    return registerPair(request, db);
  }
  const pairMatch = path.match(/^\/v1\/pairs\/([A-Za-z0-9_-]{22})$/);
  if (pairMatch && method === "DELETE") {
    return revokePair(request, db, pairMatch[1]);
  }
  const messageMatch = path.match(/^\/v1\/pairs\/([A-Za-z0-9_-]{22})\/messages$/);
  if (messageMatch && method === "POST") {
    return submitMessage(request, db, messageMatch[1]);
  }
  const deliveryStatusMatch = path.match(
    /^\/v1\/pairs\/([A-Za-z0-9_-]{22})\/deliveries\/([A-Za-z0-9_-]{22})$/,
  );
  if (deliveryStatusMatch && method === "GET") {
    return getDeliveryStatus(request, db, deliveryStatusMatch[1], deliveryStatusMatch[2]);
  }
  const receiveMatch = path.match(/^\/v1\/devices\/([A-Za-z0-9_-]{22})\/messages$/);
  if (receiveMatch && method === "GET") {
    return pollDeviceMessages(request, db, receiveMatch[1]);
  }
  const acknowledgeMatch = path.match(
    /^\/v1\/devices\/([A-Za-z0-9_-]{22})\/deliveries\/([A-Za-z0-9_-]{22})$/,
  );
  if (acknowledgeMatch && method === "POST") {
    return acknowledgeDelivery(request, db, acknowledgeMatch[1], acknowledgeMatch[2]);
  }
  throw new RelayError(404, "not_found", "Relay endpoint not found.");
}

async function createDevice(request: Request, db: D1Database): Promise<Response> {
  await enforceRateLimit(db, `device:${await clientFingerprint(request)}`, 12, 600);
  const now = unixTime();
  const deviceId = randomBase64Url(16);
  const receiverToken = randomBase64Url(32);
  await db
    .prepare(
      "INSERT INTO relay_devices (device_id, receiver_token_hash, created_at) VALUES (?, ?, ?)",
    )
    .bind(deviceId, await tokenHash(receiverToken), now)
    .run();
  return json(
    { protocol: PROTOCOL, device_id: deviceId, receiver_token: receiverToken },
    201,
  );
}

async function createPairing(request: Request, db: D1Database): Promise<Response> {
  const device = await receiverDevice(request, db);
  const body = await readJsonObject(request);
  requireExactFields(body, ["protocol"]);
  if (body.protocol !== PROTOCOL) invalidRequest("Pairing request fields are invalid.");
  const now = unixTime();
  const pairingId = randomBase64Url(16);
  const pairingToken = randomBase64Url(32);
  const expiresAt = now + PAIRING_TTL_SECONDS;
  await db
    .prepare(
      "INSERT INTO relay_pairings (pairing_id, device_id, pairing_token_hash, created_at, expires_at, status) VALUES (?, ?, ?, ?, ?, 'open')",
    )
    .bind(pairingId, device.device_id, await tokenHash(pairingToken), now, expiresAt)
    .run();
  return json(
    {
      protocol: PROTOCOL,
      pairing_id: pairingId,
      pairing_token: pairingToken,
      expires_at: expiresAt,
    },
    201,
  );
}

async function submitPairingRequest(
  request: Request,
  db: D1Database,
  pairingId: string,
): Promise<Response> {
  const pairing = await phonePairing(request, db, pairingId);
  ensurePairingActive(pairing);
  if (
    pairing.request_envelope !== null ||
    !["open", "opened"].includes(pairing.status)
  ) {
    throw new RelayError(409, "pairing_already_used", "Pairing request was already submitted.");
  }
  const envelope = await readJsonObject(request);
  validatePairingEnvelope(envelope, pairing, "pair_request");
  const result = await db
    .prepare(
      "UPDATE relay_pairings SET request_envelope = ?, status = 'requested' WHERE pairing_id = ? AND status IN ('open', 'opened') AND request_envelope IS NULL",
    )
    .bind(JSON.stringify(envelope), pairingId)
    .run();
  if ((result.meta.changes ?? 0) !== 1) {
    throw new RelayError(409, "pairing_already_used", "Pairing request was already submitted.");
  }
  return json({ status: "waiting_for_pc", pairing_id: pairingId }, 202);
}

async function markPairingOpened(
  request: Request,
  db: D1Database,
  pairingId: string,
): Promise<Response> {
  const pairing = await phonePairing(request, db, pairingId);
  ensurePairingActive(pairing);
  if (pairing.status === "cancelled_by_phone") {
    throw new RelayError(409, "pairing_cancelled", "Pairing was cancelled by the phone.");
  }
  if (pairing.status === "open") {
    await db
      .prepare("UPDATE relay_pairings SET status = 'opened' WHERE pairing_id = ? AND status = 'open'")
      .bind(pairingId)
      .run();
  }
  return json({ status: "phone_opened", pairing_id: pairingId }, 202);
}

async function cancelPairingFromPhone(
  request: Request,
  db: D1Database,
  pairingId: string,
): Promise<Response> {
  const pairing = await phonePairing(request, db, pairingId);
  ensurePairingActive(pairing);
  if (pairing.request_envelope !== null || pairing.status === "requested" || pairing.status === "complete") {
    throw new RelayError(409, "pairing_already_used", "Pairing request was already submitted.");
  }
  await db
    .prepare(
      "UPDATE relay_pairings SET status = 'cancelled_by_phone' WHERE pairing_id = ? AND status IN ('open', 'opened', 'cancelled_by_phone')",
    )
    .bind(pairingId)
    .run();
  return json({ status: "phone_cancelled", pairing_id: pairingId }, 202);
}

async function getPairingRequest(
  request: Request,
  db: D1Database,
  pairingId: string,
): Promise<Response> {
  const pairing = await receiverPairing(request, db, pairingId);
  ensurePairingActive(pairing);
  if (pairing.request_envelope === null) {
    const status = pairing.status === "cancelled_by_phone"
      ? "phone_cancelled"
      : pairing.status === "opened"
        ? "phone_opened"
        : "waiting_for_phone";
    return json({ status, pairing_id: pairingId }, 202);
  }
  return json({ envelope: JSON.parse(pairing.request_envelope) });
}

async function cancelPairing(
  request: Request,
  db: D1Database,
  pairingId: string,
): Promise<Response> {
  await receiverPairing(request, db, pairingId);
  await db.prepare("DELETE FROM relay_pairings WHERE pairing_id = ?").bind(pairingId).run();
  return json({ status: "cancelled", pairing_id: pairingId });
}

async function submitPairingResult(
  request: Request,
  db: D1Database,
  pairingId: string,
): Promise<Response> {
  const pairing = await receiverPairing(request, db, pairingId);
  ensurePairingActive(pairing);
  if (pairing.request_envelope === null || pairing.status !== "requested") {
    throw new RelayError(409, "pairing_not_ready", "No phone request is waiting.");
  }
  const envelope = await readJsonObject(request);
  validatePairingEnvelope(envelope, pairing, "pair_result");
  const requestEnvelope = JSON.parse(pairing.request_envelope) as Record<string, unknown>;
  if (envelope.phone_public_key !== requestEnvelope.phone_public_key) {
    invalidRequest("Pairing result belongs to another phone.");
  }
  const result = await db
    .prepare(
      "UPDATE relay_pairings SET result_envelope = ?, status = 'complete' WHERE pairing_id = ? AND status = 'requested' AND result_envelope IS NULL",
    )
    .bind(JSON.stringify(envelope), pairingId)
    .run();
  if ((result.meta.changes ?? 0) !== 1) {
    throw new RelayError(409, "pairing_already_complete", "Pairing result was already stored.");
  }
  return json({ status: "ready_for_phone", pairing_id: pairingId }, 202);
}

async function getPairingResult(
  request: Request,
  db: D1Database,
  pairingId: string,
): Promise<Response> {
  const pairing = await phonePairing(request, db, pairingId);
  ensurePairingActive(pairing);
  if (pairing.result_envelope === null) {
    return json({ status: "waiting_for_pc", pairing_id: pairingId }, 202);
  }
  return json({ envelope: JSON.parse(pairing.result_envelope) });
}

async function registerPair(request: Request, db: D1Database): Promise<Response> {
  const device = await receiverDevice(request, db);
  const body = await readJsonObject(request);
  requireExactFields(body, ["protocol", "pair_id", "sender_token"]);
  if (
    body.protocol !== PROTOCOL ||
    !isBase64Url(body.pair_id, 16) ||
    !isBase64Url(body.sender_token, 32)
  ) {
    invalidRequest("Pair registration fields are invalid.");
  }
  try {
    await db
      .prepare(
        "INSERT INTO relay_pairs (pair_id, device_id, sender_token_hash, created_at) VALUES (?, ?, ?, ?)",
      )
      .bind(body.pair_id, device.device_id, await tokenHash(body.sender_token), unixTime())
      .run();
  } catch (error) {
    if (isConstraintError(error)) {
      throw new RelayError(409, "pair_already_exists", "Pair route already exists.");
    }
    throw error;
  }
  return json({ status: "paired", pair_id: body.pair_id }, 201);
}

async function revokePair(
  request: Request,
  db: D1Database,
  pairId: string,
): Promise<Response> {
  const pair = await receiverPair(request, db, pairId);
  const now = unixTime();
  await db.batch([
    db.prepare("UPDATE relay_pairs SET revoked_at = ? WHERE pair_id = ?").bind(now, pairId),
    db.prepare("DELETE FROM relay_deliveries WHERE pair_id = ?").bind(pairId),
  ]);
  return json({ status: "revoked", pair_id: pair.pair_id });
}

async function submitMessage(
  request: Request,
  db: D1Database,
  pairId: string,
): Promise<Response> {
  const pair = await senderPair(request, db, pairId);
  await enforceRateLimit(db, `send:${await tokenHash(pair.sender_token_hash)}`, 60, 60);
  const now = unixTime();
  if (pair.last_seen_at === null || pair.last_seen_at === undefined || pair.last_seen_at < now - RECEIVER_ONLINE_SECONDS) {
    throw new RelayError(409, "receiver_offline", "The paired PC is not connected.");
  }
  const envelope = await readJsonObject(request);
  validateMessageEnvelope(envelope, pairId, "url_message", now);
  const deliveryId = randomBase64Url(16);
  try {
    await db
      .prepare(
        "INSERT INTO relay_deliveries (delivery_id, pair_id, device_id, message_id, envelope, created_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
      )
      .bind(
        deliveryId,
        pairId,
        pair.device_id,
        envelope.message_id,
        JSON.stringify(envelope),
        now,
        envelope.expires_at,
      )
      .run();
  } catch (error) {
    if (isConstraintError(error)) {
      throw new RelayError(409, "replay_rejected", "This encrypted message was already submitted.");
    }
    throw error;
  }
  return json({ status: "pending", delivery_id: deliveryId }, 202);
}

async function pollDeviceMessages(
  request: Request,
  db: D1Database,
  deviceId: string,
): Promise<Response> {
  await receiverDeviceById(request, db, deviceId);
  const now = unixTime();
  await db
    .prepare(
      "UPDATE relay_devices SET last_seen_at = ? WHERE device_id = ? AND (last_seen_at IS NULL OR last_seen_at < ?)",
    )
    .bind(now, deviceId, now - 5)
    .run();

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const delivery = await db
      .prepare(
        "SELECT delivery_id, pair_id, device_id, message_id, envelope, expires_at, status, ack_envelope FROM relay_deliveries WHERE device_id = ? AND expires_at >= ? AND (status = 'pending' OR (status = 'delivering' AND lease_until <= ?)) ORDER BY created_at LIMIT 1",
      )
      .bind(deviceId, now, now)
      .first<DeliveryRow>();
    if (delivery === null) return new Response(null, { status: 204 });
    const leased = await db
      .prepare(
        "UPDATE relay_deliveries SET status = 'delivering', lease_until = ? WHERE delivery_id = ? AND (status = 'pending' OR (status = 'delivering' AND lease_until <= ?))",
      )
      .bind(now + DELIVERY_LEASE_SECONDS, delivery.delivery_id, now)
      .run();
    if ((leased.meta.changes ?? 0) === 1) {
      return json({
        event: "url_message",
        delivery_id: delivery.delivery_id,
        envelope: JSON.parse(delivery.envelope),
      });
    }
  }
  return new Response(null, { status: 204 });
}

async function acknowledgeDelivery(
  request: Request,
  db: D1Database,
  deviceId: string,
  deliveryId: string,
): Promise<Response> {
  await receiverDeviceById(request, db, deviceId);
  const delivery = await db
    .prepare(
      "SELECT delivery_id, pair_id, device_id, message_id, envelope, expires_at, status, ack_envelope FROM relay_deliveries WHERE delivery_id = ? AND device_id = ?",
    )
    .bind(deliveryId, deviceId)
    .first<DeliveryRow>();
  if (delivery === null) throw new RelayError(404, "delivery_not_found", "Delivery not found.");
  if (delivery.expires_at < unixTime()) throw new RelayError(410, "delivery_expired", "Delivery expired.");
  const body = await readJsonObject(request);
  if (body.event === "delivery_error") {
    requireExactFields(body, ["event", "delivery_id"]);
    if (body.delivery_id !== deliveryId) invalidRequest("Delivery ID does not match.");
    await db
      .prepare("UPDATE relay_deliveries SET status = 'rejected', lease_until = NULL WHERE delivery_id = ?")
      .bind(deliveryId)
      .run();
    return json({ status: "rejected", delivery_id: deliveryId }, 202);
  }
  requireExactFields(body, ["event", "delivery_id", "envelope"]);
  if (body.event !== "delivery_ack" || body.delivery_id !== deliveryId || !isObject(body.envelope)) {
    invalidRequest("Delivery acknowledgement fields are invalid.");
  }
  validateMessageEnvelope(body.envelope, delivery.pair_id, "delivered_ack", unixTime());
  if (body.envelope.message_id !== delivery.message_id) {
    invalidRequest("Acknowledgement belongs to another message.");
  }
  await db
    .prepare(
      "UPDATE relay_deliveries SET status = 'delivered', ack_envelope = ?, expires_at = MIN(expires_at, ?), lease_until = NULL WHERE delivery_id = ?",
    )
    .bind(JSON.stringify(body.envelope), body.envelope.expires_at, deliveryId)
    .run();
  return json({ status: "delivered", delivery_id: deliveryId }, 202);
}

async function getDeliveryStatus(
  request: Request,
  db: D1Database,
  pairId: string,
  deliveryId: string,
): Promise<Response> {
  await senderPair(request, db, pairId);
  const delivery = await db
    .prepare(
      "SELECT delivery_id, pair_id, device_id, message_id, envelope, expires_at, status, ack_envelope FROM relay_deliveries WHERE delivery_id = ? AND pair_id = ?",
    )
    .bind(deliveryId, pairId)
    .first<DeliveryRow>();
  if (delivery === null) throw new RelayError(404, "delivery_not_found", "Delivery not found.");
  if (delivery.expires_at < unixTime()) {
    throw new RelayError(410, "delivery_expired", "Delivery expired before acknowledgement.");
  }
  if (delivery.status === "delivered" && delivery.ack_envelope !== null) {
    return json({ status: "delivered", envelope: JSON.parse(delivery.ack_envelope) });
  }
  if (delivery.status === "rejected") {
    throw new RelayError(409, "delivery_rejected", "The PC rejected the encrypted message.");
  }
  return json({ status: "pending", delivery_id: deliveryId }, 202);
}

async function receiverDevice(request: Request, db: D1Database): Promise<{ device_id: string }> {
  const hash = await tokenHash(bearerToken(request));
  const row = await db
    .prepare("SELECT device_id FROM relay_devices WHERE receiver_token_hash = ?")
    .bind(hash)
    .first<{ device_id: string }>();
  if (row === null) unauthorized();
  return row;
}

async function receiverDeviceById(
  request: Request,
  db: D1Database,
  deviceId: string,
): Promise<void> {
  const hash = await tokenHash(bearerToken(request));
  const row = await db
    .prepare("SELECT device_id FROM relay_devices WHERE device_id = ? AND receiver_token_hash = ?")
    .bind(deviceId, hash)
    .first();
  if (row === null) unauthorized();
}

async function receiverPairing(
  request: Request,
  db: D1Database,
  pairingId: string,
): Promise<PairingRow> {
  const hash = await tokenHash(bearerToken(request));
  const row = await db
    .prepare(
      "SELECT p.pairing_id, p.device_id, p.pairing_token_hash, p.expires_at, p.request_envelope, p.result_envelope, p.status FROM relay_pairings p JOIN relay_devices d ON d.device_id = p.device_id WHERE p.pairing_id = ? AND d.receiver_token_hash = ?",
    )
    .bind(pairingId, hash)
    .first<PairingRow>();
  if (row === null) unauthorized();
  return row;
}

async function phonePairing(
  request: Request,
  db: D1Database,
  pairingId: string,
): Promise<PairingRow> {
  const hash = await tokenHash(bearerToken(request));
  const row = await db
    .prepare(
      "SELECT pairing_id, device_id, pairing_token_hash, expires_at, request_envelope, result_envelope, status FROM relay_pairings WHERE pairing_id = ? AND pairing_token_hash = ?",
    )
    .bind(pairingId, hash)
    .first<PairingRow>();
  if (row === null) unauthorized();
  return row;
}

async function receiverPair(
  request: Request,
  db: D1Database,
  pairId: string,
): Promise<PairRow> {
  const hash = await tokenHash(bearerToken(request));
  const row = await db
    .prepare(
      "SELECT p.pair_id, p.device_id, p.sender_token_hash, p.revoked_at FROM relay_pairs p JOIN relay_devices d ON d.device_id = p.device_id WHERE p.pair_id = ? AND d.receiver_token_hash = ?",
    )
    .bind(pairId, hash)
    .first<PairRow>();
  if (row === null) unauthorized();
  return row;
}

async function senderPair(request: Request, db: D1Database, pairId: string): Promise<PairRow> {
  const hash = await tokenHash(bearerToken(request));
  const row = await db
    .prepare(
      "SELECT p.pair_id, p.device_id, p.sender_token_hash, p.revoked_at, d.last_seen_at FROM relay_pairs p JOIN relay_devices d ON d.device_id = p.device_id WHERE p.pair_id = ? AND p.sender_token_hash = ?",
    )
    .bind(pairId, hash)
    .first<PairRow>();
  if (row === null || row.revoked_at !== null) unauthorized();
  return row;
}

function ensurePairingActive(pairing: PairingRow): void {
  if (pairing.expires_at < unixTime()) {
    throw new RelayError(410, "pairing_expired", "The pairing code expired.");
  }
}

function validatePairingEnvelope(
  value: Record<string, unknown>,
  pairing: PairingRow,
  expectedType: "pair_request" | "pair_result",
): void {
  requireFieldSet(value, PAIRING_ENVELOPE_FIELDS);
  const now = unixTime();
  if (
    value.protocol !== PROTOCOL ||
    value.type !== expectedType ||
    value.device_id !== pairing.device_id ||
    value.pairing_id !== pairing.pairing_id ||
    value.expires_at !== pairing.expires_at ||
    !isBase64Url(value.phone_public_key, 65) ||
    !isBase64Url(value.nonce, 12) ||
    !isBase64Url(value.ciphertext, undefined, 16) ||
    !isTimestamp(value.created_at) ||
    value.created_at > now + MAX_CLOCK_SKEW_SECONDS ||
    value.created_at > pairing.expires_at
  ) {
    invalidRequest("Pairing envelope is invalid.");
  }
}

function validateMessageEnvelope(
  value: Record<string, unknown>,
  pairId: string,
  expectedType: "url_message" | "delivered_ack",
  now: number,
): void {
  requireFieldSet(value, MESSAGE_ENVELOPE_FIELDS);
  if (
    value.protocol !== PROTOCOL ||
    value.type !== expectedType ||
    value.pair_id !== pairId ||
    value.key_epoch !== 1 ||
    !isBase64Url(value.pair_id, 16) ||
    !isBase64Url(value.message_id, 16) ||
    !isBase64Url(value.nonce, 12) ||
    !isBase64Url(value.ciphertext, undefined, 16) ||
    !isTimestamp(value.created_at) ||
    !isTimestamp(value.expires_at) ||
    value.expires_at < value.created_at ||
    value.expires_at - value.created_at > (expectedType === "url_message" ? MESSAGE_TTL_SECONDS : 10) ||
    value.created_at > now + MAX_CLOCK_SKEW_SECONDS ||
    value.expires_at < now
  ) {
    invalidRequest("Encrypted message envelope is invalid.");
  }
}

async function enforceRateLimit(
  db: D1Database,
  key: string,
  limit: number,
  windowSeconds: number,
): Promise<void> {
  const now = unixTime();
  await db
    .prepare(
      "INSERT INTO relay_rate_limits (key, window_started_at, request_count, expires_at) VALUES (?, ?, 1, ?) ON CONFLICT(key) DO UPDATE SET window_started_at = CASE WHEN expires_at <= ? THEN ? ELSE window_started_at END, request_count = CASE WHEN expires_at <= ? THEN 1 ELSE request_count + 1 END, expires_at = CASE WHEN expires_at <= ? THEN ? ELSE expires_at END",
    )
    .bind(key, now, now + windowSeconds, now, now, now, now, now + windowSeconds)
    .run();
  const row = await db
    .prepare("SELECT request_count, expires_at FROM relay_rate_limits WHERE key = ?")
    .bind(key)
    .first<{ request_count: number; expires_at: number }>();
  if (row !== null && row.request_count > limit) {
    throw new RelayError(
      429,
      "rate_limited",
      "Too many relay requests.",
      Math.max(1, row.expires_at - now),
    );
  }
}

async function cleanExpiredState(db: D1Database, now: number): Promise<void> {
  await db.batch([
    db.prepare("DELETE FROM relay_pairings WHERE expires_at < ?").bind(now),
    db.prepare("DELETE FROM relay_deliveries WHERE expires_at < ?").bind(now),
    db.prepare("DELETE FROM relay_rate_limits WHERE expires_at < ?").bind(now),
  ]);
}

async function readJsonObject(request: Request): Promise<Record<string, unknown>> {
  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declaredLength) && declaredLength > MAX_REQUEST_BYTES) {
    throw new RelayError(413, "request_too_large", "Relay request is too large.");
  }
  const text = await request.text();
  if (new TextEncoder().encode(text).length > MAX_REQUEST_BYTES) {
    throw new RelayError(413, "request_too_large", "Relay request is too large.");
  }
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    invalidRequest("Request body must be valid JSON.");
  }
  if (!isObject(value)) invalidRequest("Request body must be a JSON object.");
  return value;
}

function bearerToken(request: Request): string {
  const match = request.headers.get("authorization")?.match(/^Bearer ([A-Za-z0-9_-]{43})$/);
  if (!match) unauthorized();
  return match[1];
}

async function tokenHash(token: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return base64Url(new Uint8Array(digest));
}

async function clientFingerprint(request: Request): Promise<string> {
  const address = request.headers.get("cf-connecting-ip") ?? "unknown";
  return tokenHash(address);
}

function randomBase64Url(bytes: number): string {
  return base64Url(crypto.getRandomValues(new Uint8Array(bytes)));
}

function base64Url(value: Uint8Array): string {
  let binary = "";
  for (const byte of value) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function isBase64Url(value: unknown, bytes?: number, minimumBytes?: number): value is string {
  if (typeof value !== "string" || !/^[A-Za-z0-9_-]+$/.test(value) || value.includes("=")) return false;
  try {
    const base64 = value.replaceAll("-", "+").replaceAll("_", "/");
    const binary = atob(base64 + "=".repeat((4 - (base64.length % 4)) % 4));
    if (bytes !== undefined && binary.length !== bytes) return false;
    if (minimumBytes !== undefined && binary.length < minimumBytes) return false;
    return base64Url(Uint8Array.from(binary, (character) => character.charCodeAt(0))) === value;
  } catch {
    return false;
  }
}

function isTimestamp(value: unknown): value is number {
  return Number.isSafeInteger(value) && typeof value === "number" && value >= 0;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireExactFields(value: Record<string, unknown>, fields: string[]): void {
  requireFieldSet(value, new Set(fields));
}

function requireFieldSet(value: Record<string, unknown>, fields: Set<string>): void {
  const keys = Object.keys(value);
  if (keys.length !== fields.size || keys.some((key) => !fields.has(key))) {
    invalidRequest("Request fields are invalid.");
  }
}

function json(value: unknown, status = 200): Response {
  return Response.json(value, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

function relayError(error: RelayError): Response {
  const body: Record<string, unknown> = {
    error: { code: error.code, message: error.message },
  };
  if (error.retryAfterSeconds !== undefined) {
    (body.error as Record<string, unknown>).retry_after_seconds = error.retryAfterSeconds;
  }
  return json(body, error.status);
}

function invalidRequest(message: string): never {
  throw new RelayError(400, "invalid_request", message);
}

function unauthorized(): never {
  throw new RelayError(401, "unauthorized", "Relay credential is invalid.");
}

function isConstraintError(error: unknown): boolean {
  return error instanceof Error && /constraint|unique/i.test(error.message);
}

function unixTime(): number {
  return Math.floor(Date.now() / 1000);
}
