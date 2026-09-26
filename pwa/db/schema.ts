import { index, integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const relayDevices = sqliteTable(
  "relay_devices",
  {
    deviceId: text("device_id").primaryKey(),
    receiverTokenHash: text("receiver_token_hash").notNull(),
    createdAt: integer("created_at").notNull(),
    lastSeenAt: integer("last_seen_at"),
  },
  (table) => [uniqueIndex("relay_devices_receiver_token_uq").on(table.receiverTokenHash)],
);

export const relayPairings = sqliteTable(
  "relay_pairings",
  {
    pairingId: text("pairing_id").primaryKey(),
    deviceId: text("device_id").notNull(),
    pairingTokenHash: text("pairing_token_hash").notNull(),
    createdAt: integer("created_at").notNull(),
    expiresAt: integer("expires_at").notNull(),
    requestEnvelope: text("request_envelope"),
    resultEnvelope: text("result_envelope"),
    status: text("status").notNull(),
  },
  (table) => [
    uniqueIndex("relay_pairings_token_uq").on(table.pairingTokenHash),
    index("relay_pairings_device_idx").on(table.deviceId),
    index("relay_pairings_expiry_idx").on(table.expiresAt),
  ],
);

export const relayPairs = sqliteTable(
  "relay_pairs",
  {
    pairId: text("pair_id").primaryKey(),
    deviceId: text("device_id").notNull(),
    senderTokenHash: text("sender_token_hash").notNull(),
    createdAt: integer("created_at").notNull(),
    revokedAt: integer("revoked_at"),
  },
  (table) => [
    uniqueIndex("relay_pairs_sender_token_uq").on(table.senderTokenHash),
    index("relay_pairs_device_idx").on(table.deviceId),
  ],
);

export const relayDeliveries = sqliteTable(
  "relay_deliveries",
  {
    deliveryId: text("delivery_id").primaryKey(),
    pairId: text("pair_id").notNull(),
    deviceId: text("device_id").notNull(),
    messageId: text("message_id").notNull(),
    envelope: text("envelope").notNull(),
    createdAt: integer("created_at").notNull(),
    expiresAt: integer("expires_at").notNull(),
    leaseUntil: integer("lease_until"),
    status: text("status").notNull(),
    ackEnvelope: text("ack_envelope"),
  },
  (table) => [
    uniqueIndex("relay_deliveries_pair_message_uq").on(table.pairId, table.messageId),
    index("relay_deliveries_device_status_idx").on(table.deviceId, table.status, table.createdAt),
    index("relay_deliveries_expiry_idx").on(table.expiresAt),
  ],
);

export const relayRateLimits = sqliteTable("relay_rate_limits", {
  key: text("key").primaryKey(),
  windowStartedAt: integer("window_started_at").notNull(),
  requestCount: integer("request_count").notNull(),
  expiresAt: integer("expires_at").notNull(),
});
