import { SupabaseAdmin, SupabaseAdminError } from "./supabase-admin.ts";
import {
  SupabaseConfigurationError,
  supabasePublicConfig,
  supabaseServerConfig,
} from "./supabase-config.ts";

const PROTOCOL = "wqrs/1";
const PAIRING_TTL_SECONDS = 120;
const MESSAGE_TTL_SECONDS = 300;
const MAX_CLOCK_SKEW_SECONDS = 120;
const RECEIVER_ONLINE_SECONDS = 75;
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

interface DeviceRow {
  device_id: string;
  receiver_token_hash: string;
  realtime_user_id: string;
  last_seen_at: number | null;
}

interface PairingRow {
  pairing_id: string;
  device_id: string;
  pairing_token_hash: string;
  expires_at: number;
  request_envelope: Record<string, unknown> | null;
  result_envelope: Record<string, unknown> | null;
  status: string;
}

interface PairRow {
  pair_id: string;
  device_id: string;
  sender_token_hash: string;
  revoked_at: number | null;
  last_seen_at?: number | null;
}

interface DeliveryRow {
  delivery_id: string;
  pair_id: string;
  device_id: string;
  message_id: string;
  envelope: Record<string, unknown>;
  expires_at: number;
  status: string;
  ack_envelope: Record<string, unknown> | null;
}

interface RateLimitResult {
  allowed: boolean;
  retry_after: number;
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

export async function handleRelayRequest(request: Request): Promise<Response> {
  const url = new URL(request.url);

  try {
    const admin = new SupabaseAdmin();
    if ((crypto.getRandomValues(new Uint8Array(1))[0] & 63) === 0) {
      try {
        await admin.rpc("relay_cleanup", { p_now: unixTime() });
      } catch (error) {
        // Cleanup is maintenance, not part of the user request. A temporary
        // database failure must not turn an otherwise valid relay call into
        // an error or leave a rejected promise behind after Vercel freezes
        // the invocation.
        if (error instanceof SupabaseAdminError) {
          console.warn("Relay cleanup was skipped.", { code: error.code });
        }
      }
    }
    return await routeRelayRequest(request, url, admin);
  } catch (error) {
    if (error instanceof RelayError) return relayError(error);
    if (error instanceof SupabaseAdminError) {
      if (error.code === "23505") {
        return relayError(
          new RelayError(409, "conflict", "The relay record already exists."),
        );
      }
      if (error.code === "realtime_auth_required") {
        return relayError(new RelayError(401, error.code, error.message));
      }
      console.error("Supabase relay request failed", error.code);
      return relayError(
        new RelayError(503, "relay_unavailable", "The relay is temporarily unavailable."),
      );
    }
    if (error instanceof SupabaseConfigurationError) {
      return relayError(
        new RelayError(
          503,
          "deployment_not_configured",
          "The relay deployment is not configured yet.",
        ),
      );
    }
    console.error("Relay request failed", error);
    return relayError(
      new RelayError(500, "internal_error", "The relay could not process the request."),
    );
  }
}

async function routeRelayRequest(
  request: Request,
  url: URL,
  admin: SupabaseAdmin,
): Promise<Response> {
  const method = request.method.toUpperCase();
  const path = url.pathname;

  if (method === "GET" && path === "/healthz") {
    return json({ status: "ok", protocol: PROTOCOL, transport: "supabase-realtime" });
  }
  if (method === "GET" && path === "/v1/realtime/config") {
    return json({
      protocol: PROTOCOL,
      ...supabasePublicConfig(),
      fallback_poll_seconds: 5,
      connected_resync_seconds: 60,
    });
  }
  if (method === "POST" && path === "/v1/devices") {
    return createDevice(request, admin);
  }
  if (method === "POST" && path === "/v1/pairings") {
    return createPairing(request, admin);
  }

  const pairingMatch = path.match(
    /^\/v1\/pairings\/([A-Za-z0-9_-]{22})(?:\/(request|result|opened|phone-cancel))?$/,
  );
  if (pairingMatch) {
    const [, pairingId, action] = pairingMatch;
    if (method === "DELETE" && action === undefined) {
      return cancelPairing(request, admin, pairingId);
    }
    if (action === "request" && method === "POST") {
      return submitPairingRequest(request, admin, pairingId);
    }
    if (action === "request" && method === "GET") {
      return getPairingRequest(request, admin, pairingId);
    }
    if (action === "opened" && method === "POST") {
      return markPairingOpened(request, admin, pairingId);
    }
    if (action === "phone-cancel" && method === "POST") {
      return cancelPairingFromPhone(request, admin, pairingId);
    }
    if (action === "result" && method === "POST") {
      return submitPairingResult(request, admin, pairingId);
    }
    if (action === "result" && method === "GET") {
      return getPairingResult(request, admin, pairingId);
    }
  }

  if (method === "POST" && path === "/v1/pairs") {
    return registerPair(request, admin);
  }
  const pairMatch = path.match(/^\/v1\/pairs\/([A-Za-z0-9_-]{22})$/);
  if (pairMatch && method === "DELETE") {
    return revokePair(request, admin, pairMatch[1]);
  }
  const messageMatch = path.match(
    /^\/v1\/pairs\/([A-Za-z0-9_-]{22})\/messages$/,
  );
  if (messageMatch && method === "POST") {
    return submitMessage(request, admin, messageMatch[1]);
  }
  const deliveryStatusMatch = path.match(
    /^\/v1\/pairs\/([A-Za-z0-9_-]{22})\/deliveries\/([A-Za-z0-9_-]{22})$/,
  );
  if (deliveryStatusMatch && method === "GET") {
    return getDeliveryStatus(
      request,
      admin,
      deliveryStatusMatch[1],
      deliveryStatusMatch[2],
    );
  }
  const receiveMatch = path.match(
    /^\/v1\/devices\/([A-Za-z0-9_-]{22})\/messages$/,
  );
  if (receiveMatch && method === "GET") {
    return pollDeviceMessages(request, admin, receiveMatch[1]);
  }
  const acknowledgeMatch = path.match(
    /^\/v1\/devices\/([A-Za-z0-9_-]{22})\/deliveries\/([A-Za-z0-9_-]{22})$/,
  );
  if (acknowledgeMatch && method === "POST") {
    return acknowledgeDelivery(
      request,
      admin,
      acknowledgeMatch[1],
      acknowledgeMatch[2],
    );
  }
  throw new RelayError(404, "not_found", "Relay endpoint not found.");
}

async function createDevice(request: Request, admin: SupabaseAdmin): Promise<Response> {
  await enforceRateLimit(
    admin,
    `device:${await clientFingerprint(request)}`,
    12,
    600,
  );
  const realtimeUserId = await admin.authenticatedUserId(accessToken(request));
  const now = unixTime();
  const deviceId = randomBase64Url(16);
  const receiverToken = randomBase64Url(32);
  await admin.insert("relay_devices", {
    device_id: deviceId,
    receiver_token_hash: await tokenHash(receiverToken),
    realtime_user_id: realtimeUserId,
    created_at: now,
  });
  return json(
    { protocol: PROTOCOL, device_id: deviceId, receiver_token: receiverToken },
    201,
  );
}

async function createPairing(request: Request, admin: SupabaseAdmin): Promise<Response> {
  const device = await receiverDevice(request, admin);
  const body = await readJsonObject(request);
  requireExactFields(body, ["protocol"]);
  if (body.protocol !== PROTOCOL) invalidRequest("Pairing request fields are invalid.");
  const now = unixTime();
  const pairingId = randomBase64Url(16);
  const pairingToken = randomBase64Url(32);
  const expiresAt = now + PAIRING_TTL_SECONDS;
  await admin.insert("relay_pairings", {
    pairing_id: pairingId,
    device_id: device.device_id,
    pairing_token_hash: await tokenHash(pairingToken),
    created_at: now,
    expires_at: expiresAt,
    status: "open",
  });
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
  admin: SupabaseAdmin,
  pairingId: string,
): Promise<Response> {
  const pairing = await phonePairing(request, admin, pairingId);
  ensurePairingActive(pairing);
  if (pairing.request_envelope !== null || !["open", "opened"].includes(pairing.status)) {
    throw new RelayError(409, "pairing_already_used", "Pairing request was already submitted.");
  }
  const envelope = await readJsonObject(request);
  validatePairingEnvelope(envelope, pairing, "pair_request");
  const rows = await admin.update<PairingRow>(
    "relay_pairings",
    filters({
      pairing_id: `eq.${pairingId}`,
      status: "in.(open,opened)",
      request_envelope: "is.null",
    }),
    { request_envelope: envelope, status: "requested" },
  );
  if (rows.length !== 1) {
    throw new RelayError(409, "pairing_already_used", "Pairing request was already submitted.");
  }
  return json({ status: "waiting_for_pc", pairing_id: pairingId }, 202);
}

async function markPairingOpened(
  request: Request,
  admin: SupabaseAdmin,
  pairingId: string,
): Promise<Response> {
  const pairing = await phonePairing(request, admin, pairingId);
  ensurePairingActive(pairing);
  if (pairing.status === "cancelled_by_phone") {
    throw new RelayError(409, "pairing_cancelled", "Pairing was cancelled by the phone.");
  }
  if (pairing.status === "open") {
    await admin.update(
      "relay_pairings",
      filters({ pairing_id: `eq.${pairingId}`, status: "eq.open" }),
      { status: "opened" },
    );
  }
  return json({ status: "phone_opened", pairing_id: pairingId }, 202);
}

async function cancelPairingFromPhone(
  request: Request,
  admin: SupabaseAdmin,
  pairingId: string,
): Promise<Response> {
  const pairing = await phonePairing(request, admin, pairingId);
  ensurePairingActive(pairing);
  if (
    pairing.request_envelope !== null ||
    pairing.status === "requested" ||
    pairing.status === "complete"
  ) {
    throw new RelayError(409, "pairing_already_used", "Pairing request was already submitted.");
  }
  await admin.update(
    "relay_pairings",
    filters({
      pairing_id: `eq.${pairingId}`,
      status: "in.(open,opened,cancelled_by_phone)",
    }),
    { status: "cancelled_by_phone" },
  );
  return json({ status: "phone_cancelled", pairing_id: pairingId }, 202);
}

async function getPairingRequest(
  request: Request,
  admin: SupabaseAdmin,
  pairingId: string,
): Promise<Response> {
  const pairing = await receiverPairing(request, admin, pairingId);
  ensurePairingActive(pairing);
  if (pairing.request_envelope === null) {
    const status =
      pairing.status === "cancelled_by_phone"
        ? "phone_cancelled"
        : pairing.status === "opened"
          ? "phone_opened"
          : "waiting_for_phone";
    return json({ status, pairing_id: pairingId }, 202);
  }
  return json({ envelope: pairing.request_envelope });
}

async function cancelPairing(
  request: Request,
  admin: SupabaseAdmin,
  pairingId: string,
): Promise<Response> {
  await receiverPairing(request, admin, pairingId);
  await admin.delete("relay_pairings", filters({ pairing_id: `eq.${pairingId}` }));
  return json({ status: "cancelled", pairing_id: pairingId });
}

async function submitPairingResult(
  request: Request,
  admin: SupabaseAdmin,
  pairingId: string,
): Promise<Response> {
  const pairing = await receiverPairing(request, admin, pairingId);
  ensurePairingActive(pairing);
  if (pairing.request_envelope === null || pairing.status !== "requested") {
    throw new RelayError(409, "pairing_not_ready", "No phone request is waiting.");
  }
  const envelope = await readJsonObject(request);
  validatePairingEnvelope(envelope, pairing, "pair_result");
  if (envelope.phone_public_key !== pairing.request_envelope.phone_public_key) {
    invalidRequest("Pairing result belongs to another phone.");
  }
  const rows = await admin.update<PairingRow>(
    "relay_pairings",
    filters({
      pairing_id: `eq.${pairingId}`,
      status: "eq.requested",
      result_envelope: "is.null",
    }),
    { result_envelope: envelope, status: "complete" },
  );
  if (rows.length !== 1) {
    throw new RelayError(409, "pairing_already_complete", "Pairing result was already stored.");
  }
  return json({ status: "ready_for_phone", pairing_id: pairingId }, 202);
}

async function getPairingResult(
  request: Request,
  admin: SupabaseAdmin,
  pairingId: string,
): Promise<Response> {
  const pairing = await phonePairing(request, admin, pairingId);
  ensurePairingActive(pairing);
  if (pairing.result_envelope === null) {
    return json({ status: "waiting_for_pc", pairing_id: pairingId }, 202);
  }
  return json({ envelope: pairing.result_envelope });
}

async function registerPair(request: Request, admin: SupabaseAdmin): Promise<Response> {
  const device = await receiverDevice(request, admin);
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
    await admin.insert("relay_pairs", {
      pair_id: body.pair_id,
      device_id: device.device_id,
      sender_token_hash: await tokenHash(body.sender_token),
      created_at: unixTime(),
    });
  } catch (error) {
    if (isUniqueViolation(error)) {
      throw new RelayError(409, "pair_already_exists", "Pair route already exists.");
    }
    throw error;
  }
  return json({ status: "paired", pair_id: body.pair_id }, 201);
}

async function revokePair(
  request: Request,
  admin: SupabaseAdmin,
  pairId: string,
): Promise<Response> {
  const pair = await receiverPair(request, admin, pairId);
  await admin.update(
    "relay_pairs",
    filters({ pair_id: `eq.${pairId}` }),
    { revoked_at: unixTime() },
  );
  await admin.delete("relay_deliveries", filters({ pair_id: `eq.${pairId}` }));
  return json({ status: "revoked", pair_id: pair.pair_id });
}

async function submitMessage(
  request: Request,
  admin: SupabaseAdmin,
  pairId: string,
): Promise<Response> {
  const pair = await senderPair(request, admin, pairId);
  await enforceRateLimit(admin, `send:${pair.sender_token_hash}`, 60, 60);
  const now = unixTime();
  if (
    pair.last_seen_at === null ||
    pair.last_seen_at === undefined ||
    pair.last_seen_at < now - RECEIVER_ONLINE_SECONDS
  ) {
    throw new RelayError(409, "receiver_offline", "The paired PC is not connected.");
  }
  const envelope = await readJsonObject(request);
  validateMessageEnvelope(envelope, pairId, "url_message", now);
  const deliveryId = randomBase64Url(16);
  try {
    await admin.insert("relay_deliveries", {
      delivery_id: deliveryId,
      pair_id: pairId,
      device_id: pair.device_id,
      message_id: envelope.message_id,
      envelope,
      created_at: now,
      expires_at: envelope.expires_at,
      status: "pending",
    });
  } catch (error) {
    if (isUniqueViolation(error)) {
      throw new RelayError(409, "replay_rejected", "This encrypted message was already submitted.");
    }
    throw error;
  }
  return json({ status: "pending", delivery_id: deliveryId }, 202);
}

async function pollDeviceMessages(
  request: Request,
  admin: SupabaseAdmin,
  deviceId: string,
): Promise<Response> {
  await receiverDeviceById(request, admin, deviceId);
  const now = unixTime();
  await admin.update(
    "relay_devices",
    filters({ device_id: `eq.${deviceId}`, last_seen_at: `lt.${now - 4}` }),
    { last_seen_at: now },
  );
  // A NULL heartbeat also needs its first update.
  await admin.update(
    "relay_devices",
    filters({ device_id: `eq.${deviceId}`, last_seen_at: "is.null" }),
    { last_seen_at: now },
  );

  const deliveries = await admin.rpc<DeliveryRow[]>("relay_claim_delivery", {
    p_device_id: deviceId,
    p_now: now,
    p_lease_until: now + DELIVERY_LEASE_SECONDS,
  });
  const delivery = deliveries[0];
  if (!delivery) return new Response(null, { status: 204 });
  return json({
    event: "url_message",
    delivery_id: delivery.delivery_id,
    envelope: delivery.envelope,
  });
}

async function acknowledgeDelivery(
  request: Request,
  admin: SupabaseAdmin,
  deviceId: string,
  deliveryId: string,
): Promise<Response> {
  await receiverDeviceById(request, admin, deviceId);
  const delivery = await selectOne<DeliveryRow>(
    admin,
    "relay_deliveries",
    filters({ delivery_id: `eq.${deliveryId}`, device_id: `eq.${deviceId}` }),
  );
  if (!delivery) throw new RelayError(404, "delivery_not_found", "Delivery not found.");
  if (delivery.expires_at < unixTime()) {
    throw new RelayError(410, "delivery_expired", "Delivery expired.");
  }
  const body = await readJsonObject(request);
  if (body.event === "delivery_error") {
    requireExactFields(body, ["event", "delivery_id"]);
    if (body.delivery_id !== deliveryId) invalidRequest("Delivery ID does not match.");
    await admin.update(
      "relay_deliveries",
      filters({ delivery_id: `eq.${deliveryId}` }),
      { status: "rejected", lease_until: null },
    );
    return json({ status: "rejected", delivery_id: deliveryId }, 202);
  }
  requireExactFields(body, ["event", "delivery_id", "envelope"]);
  if (
    body.event !== "delivery_ack" ||
    body.delivery_id !== deliveryId ||
    !isObject(body.envelope)
  ) {
    invalidRequest("Delivery acknowledgement fields are invalid.");
  }
  validateMessageEnvelope(body.envelope, delivery.pair_id, "delivered_ack", unixTime());
  if (body.envelope.message_id !== delivery.message_id) {
    invalidRequest("Acknowledgement belongs to another message.");
  }
  await admin.update(
    "relay_deliveries",
    filters({ delivery_id: `eq.${deliveryId}` }),
    {
      status: "delivered",
      ack_envelope: body.envelope,
      expires_at: Math.min(delivery.expires_at, body.envelope.expires_at as number),
      lease_until: null,
    },
  );
  return json({ status: "delivered", delivery_id: deliveryId }, 202);
}

async function getDeliveryStatus(
  request: Request,
  admin: SupabaseAdmin,
  pairId: string,
  deliveryId: string,
): Promise<Response> {
  await senderPair(request, admin, pairId);
  const delivery = await selectOne<DeliveryRow>(
    admin,
    "relay_deliveries",
    filters({ delivery_id: `eq.${deliveryId}`, pair_id: `eq.${pairId}` }),
  );
  if (!delivery) throw new RelayError(404, "delivery_not_found", "Delivery not found.");
  if (delivery.expires_at < unixTime()) {
    throw new RelayError(410, "delivery_expired", "Delivery expired before acknowledgement.");
  }
  if (delivery.status === "delivered" && delivery.ack_envelope !== null) {
    return json({ status: "delivered", envelope: delivery.ack_envelope });
  }
  if (delivery.status === "rejected") {
    throw new RelayError(409, "delivery_rejected", "The PC rejected the encrypted message.");
  }
  return json({ status: "pending", delivery_id: deliveryId }, 202);
}

async function receiverDevice(request: Request, admin: SupabaseAdmin): Promise<DeviceRow> {
  const hash = await tokenHash(bearerToken(request));
  const device = await selectOne<DeviceRow>(
    admin,
    "relay_devices",
    filters({ receiver_token_hash: `eq.${hash}` }),
  );
  if (!device) unauthorized();
  return device;
}

async function receiverDeviceById(
  request: Request,
  admin: SupabaseAdmin,
  deviceId: string,
): Promise<DeviceRow> {
  const hash = await tokenHash(bearerToken(request));
  const device = await selectOne<DeviceRow>(
    admin,
    "relay_devices",
    filters({ device_id: `eq.${deviceId}`, receiver_token_hash: `eq.${hash}` }),
  );
  if (!device) unauthorized();
  return device;
}

async function receiverPairing(
  request: Request,
  admin: SupabaseAdmin,
  pairingId: string,
): Promise<PairingRow> {
  const device = await receiverDevice(request, admin);
  const pairing = await selectOne<PairingRow>(
    admin,
    "relay_pairings",
    filters({ pairing_id: `eq.${pairingId}`, device_id: `eq.${device.device_id}` }),
  );
  if (!pairing) unauthorized();
  return pairing;
}

async function phonePairing(
  request: Request,
  admin: SupabaseAdmin,
  pairingId: string,
): Promise<PairingRow> {
  const hash = await tokenHash(bearerToken(request));
  const pairing = await selectOne<PairingRow>(
    admin,
    "relay_pairings",
    filters({ pairing_id: `eq.${pairingId}`, pairing_token_hash: `eq.${hash}` }),
  );
  if (!pairing) unauthorized();
  return pairing;
}

async function receiverPair(
  request: Request,
  admin: SupabaseAdmin,
  pairId: string,
): Promise<PairRow> {
  const device = await receiverDevice(request, admin);
  const pair = await selectOne<PairRow>(
    admin,
    "relay_pairs",
    filters({ pair_id: `eq.${pairId}`, device_id: `eq.${device.device_id}` }),
  );
  if (!pair) unauthorized();
  return pair;
}

async function senderPair(
  request: Request,
  admin: SupabaseAdmin,
  pairId: string,
): Promise<PairRow> {
  const hash = await tokenHash(bearerToken(request));
  const pair = await selectOne<PairRow>(
    admin,
    "relay_pairs",
    filters({ pair_id: `eq.${pairId}`, sender_token_hash: `eq.${hash}` }),
  );
  if (!pair || pair.revoked_at !== null) unauthorized();
  const device = await selectOne<DeviceRow>(
    admin,
    "relay_devices",
    filters({ device_id: `eq.${pair.device_id}` }),
  );
  if (!device) unauthorized();
  return { ...pair, last_seen_at: device.last_seen_at };
}

async function selectOne<T>(
  admin: SupabaseAdmin,
  table: string,
  query: URLSearchParams,
): Promise<T | null> {
  query.set("select", "*");
  query.set("limit", "1");
  const rows = await admin.select<T>(table, query);
  return rows[0] ?? null;
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
    value.expires_at - value.created_at >
      (expectedType === "url_message" ? MESSAGE_TTL_SECONDS : 10) ||
    value.created_at > now + MAX_CLOCK_SKEW_SECONDS ||
    value.expires_at < now
  ) {
    invalidRequest("Encrypted message envelope is invalid.");
  }
}

async function enforceRateLimit(
  admin: SupabaseAdmin,
  key: string,
  limit: number,
  windowSeconds: number,
): Promise<void> {
  const result = await admin.rpc<RateLimitResult[]>("relay_consume_rate_limit", {
    p_key: key,
    p_limit: limit,
    p_window_seconds: windowSeconds,
    p_now: unixTime(),
  });
  const value = result[0];
  if (!value?.allowed) {
    throw new RelayError(
      429,
      "rate_limited",
      "Too many relay requests.",
      Math.max(1, value?.retry_after ?? windowSeconds),
    );
  }
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

function accessToken(request: Request): string {
  const match = request.headers.get("authorization")?.match(/^Bearer ([A-Za-z0-9._~-]+)$/);
  if (!match || match[1].length < 40 || match[1].length > 4096) {
    throw new RelayError(401, "realtime_auth_required", "A Realtime session is required.");
  }
  return match[1];
}

function bearerToken(request: Request): string {
  const match = request.headers.get("authorization")?.match(/^Bearer ([A-Za-z0-9_-]{43})$/);
  if (!match) unauthorized();
  return match[1];
}

async function tokenHash(token: string): Promise<string> {
  const digest = new Uint8Array(
    await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token)),
  );
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function clientFingerprint(request: Request): Promise<string> {
  const forwarded =
    request.headers.get("x-vercel-forwarded-for") ??
    request.headers.get("x-forwarded-for") ??
    request.headers.get("x-real-ip") ??
    "unknown";
  const address = forwarded.split(",", 1)[0].trim();
  const { rateLimitPepper } = supabaseServerConfig();
  return tokenHash(`${rateLimitPepper}\0${address}`);
}

function randomBase64Url(bytes: number): string {
  return base64Url(crypto.getRandomValues(new Uint8Array(bytes)));
}

function base64Url(value: Uint8Array): string {
  return Buffer.from(value).toString("base64url");
}

function isBase64Url(
  value: unknown,
  bytes?: number,
  minimumBytes?: number,
): value is string {
  if (
    typeof value !== "string" ||
    !/^[A-Za-z0-9_-]+$/.test(value) ||
    value.includes("=")
  ) {
    return false;
  }
  try {
    const decoded = Buffer.from(value, "base64url");
    if (bytes !== undefined && decoded.length !== bytes) return false;
    if (minimumBytes !== undefined && decoded.length < minimumBytes) return false;
    return decoded.toString("base64url") === value;
  } catch {
    return false;
  }
}

function isTimestamp(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireExactFields(value: Record<string, unknown>, fieldNames: string[]): void {
  requireFieldSet(value, new Set(fieldNames));
}

function requireFieldSet(value: Record<string, unknown>, fieldNames: Set<string>): void {
  const keys = Object.keys(value);
  if (keys.length !== fieldNames.size || keys.some((key) => !fieldNames.has(key))) {
    invalidRequest("Request fields are invalid.");
  }
}

function filters(values: Record<string, string>): URLSearchParams {
  const result = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) result.set(key, value);
  return result;
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

function isUniqueViolation(error: unknown): boolean {
  return error instanceof SupabaseAdminError && error.code === "23505";
}

function unixTime(): number {
  return Math.floor(Date.now() / 1000);
}
