CREATE TABLE `relay_deliveries` (
	`delivery_id` text PRIMARY KEY NOT NULL,
	`pair_id` text NOT NULL,
	`device_id` text NOT NULL,
	`message_id` text NOT NULL,
	`envelope` text NOT NULL,
	`created_at` integer NOT NULL,
	`expires_at` integer NOT NULL,
	`lease_until` integer,
	`status` text NOT NULL,
	`ack_envelope` text
);
--> statement-breakpoint
CREATE UNIQUE INDEX `relay_deliveries_pair_message_uq` ON `relay_deliveries` (`pair_id`,`message_id`);--> statement-breakpoint
CREATE INDEX `relay_deliveries_device_status_idx` ON `relay_deliveries` (`device_id`,`status`,`created_at`);--> statement-breakpoint
CREATE INDEX `relay_deliveries_expiry_idx` ON `relay_deliveries` (`expires_at`);--> statement-breakpoint
CREATE TABLE `relay_devices` (
	`device_id` text PRIMARY KEY NOT NULL,
	`receiver_token_hash` text NOT NULL,
	`created_at` integer NOT NULL,
	`last_seen_at` integer
);
--> statement-breakpoint
CREATE UNIQUE INDEX `relay_devices_receiver_token_uq` ON `relay_devices` (`receiver_token_hash`);--> statement-breakpoint
CREATE TABLE `relay_pairings` (
	`pairing_id` text PRIMARY KEY NOT NULL,
	`device_id` text NOT NULL,
	`pairing_token_hash` text NOT NULL,
	`created_at` integer NOT NULL,
	`expires_at` integer NOT NULL,
	`request_envelope` text,
	`result_envelope` text,
	`status` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `relay_pairings_token_uq` ON `relay_pairings` (`pairing_token_hash`);--> statement-breakpoint
CREATE INDEX `relay_pairings_device_idx` ON `relay_pairings` (`device_id`);--> statement-breakpoint
CREATE INDEX `relay_pairings_expiry_idx` ON `relay_pairings` (`expires_at`);--> statement-breakpoint
CREATE TABLE `relay_pairs` (
	`pair_id` text PRIMARY KEY NOT NULL,
	`device_id` text NOT NULL,
	`sender_token_hash` text NOT NULL,
	`created_at` integer NOT NULL,
	`revoked_at` integer
);
--> statement-breakpoint
CREATE UNIQUE INDEX `relay_pairs_sender_token_uq` ON `relay_pairs` (`sender_token_hash`);--> statement-breakpoint
CREATE INDEX `relay_pairs_device_idx` ON `relay_pairs` (`device_id`);--> statement-breakpoint
CREATE TABLE `relay_rate_limits` (
	`key` text PRIMARY KEY NOT NULL,
	`window_started_at` integer NOT NULL,
	`request_count` integer NOT NULL,
	`expires_at` integer NOT NULL
);
