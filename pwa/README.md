# QR Scanner Phone-to-PC PWA

This directory contains the install-free mobile web companion for Webcam QR
Scanner and the Vercel-hosted relay API. The WQRS/1 cryptographic contract stays
shared with the Python desktop application while deployment-specific code stays
inside this directory.

> **Release channel:** v0.2.0 targets the stable Windows / Vercel + Supabase
> service at `https://qrwebcam.vercel.app`. Human protocol/cryptography review
> remains outstanding and was explicitly accepted by the maintainer; see
> [release notes and limitations](../docs/v0.2.0-release-notes.md).

## Current scope

The current PWA milestone includes:

- a responsive mobile application shell;
- optional PWA metadata and platform icons without installation promotion;
- a minimal service worker that caches no URL, token, key or relay response;
- first-party-only runtime resources;
- restrictive security and permissions headers;
- a camera scanner started only by an explicit user action;
- on-device QR decoding with a pinned, locally bundled decoder;
- strict HTTP/HTTPS URL validation and a result confirmation screen;
- WQRS/1 pairing with browser-native P-256, HKDF-SHA-256 and AES-256-GCM;
- normal-camera HTTPS pairing links whose one-time material stays in the URL
  fragment and is cleared from the address bar after local consumption;
- existing-pair detection with an explicit replacement choice;
- short-lived browser-open and phone-cancel signals plus automatic completion
  after the phone opens the desktop's single-use pairing QR;
- saved-pair validation before reuse, with first-scan re-pairing after desktop
  access is revoked;
- non-extractable root-key persistence in IndexedDB;
- end-to-end encrypted **Send to PC** with an authenticated delivery receipt;
- automatic camera cleanup when the scanner closes or the page is hidden;
- a Supabase Postgres relay schema that stores only short-lived opaque
  envelopes and refuses messages when the PC receiver is offline;
- private Supabase Realtime device wake-ups with a five-second recovery poll;
- anonymous, device-only Realtime authentication with no email or phone number;
- exact `pair_revoked` handling that removes only the revoked IndexedDB pairing
  and offers pairing again while preserving the scanned URL;
- automated shell, URL-policy, protocol-vector, D1 compatibility, Vercel relay,
  manifest, cache-policy and security-header tests.

**Open link in new tab**, browser pairing, and encrypted **Send to PC** are
available through the Vercel production service. Remove-and-repair flows have
user-confirmed Safari/iPhone 15 Plus and Samsung Internet/S24 FE evidence;
this is not a complete browser-version matrix. Independent human security
review remains outstanding and was explicitly accepted for v0.2.0.

## Local development

```powershell
npm install
npm run dev
```

Run validation with:

```powershell
npm test
npm run lint
```

Relay endpoints additionally require the values documented in `.env.example`.
Never put a real `SUPABASE_SECRET_KEY` in source control or client code. The
Supabase schema is in
`../supabase/migrations/202608030001_phone_to_pc_relay.sql`; the Turkish cutover
runbook is in `../docs/vercel-supabase-migration.tr.md`.
The deployment and real-device release gates are tracked in
`../docs/v0.2-beta-release-checklist.md`.

## Relay health and dependency deadlines

These endpoints describe the current source; they become available on a hosted
environment only after that source is deployed there.

- `GET /healthz` preserves the existing liveness/configuration response. It does
  not contact Supabase, so HTTP 200 does not prove that delivery is possible.
- `GET /readyz` verifies a read-only PostgREST query against `relay_devices`,
  selecting `device_id` with `limit=0`. It loads no device rows and returns only
  `{ "status": "ready", "protocol": "wqrs/1", "database": "ok" }`, or a generic
  non-cacheable 503 on failure. It does not test Realtime or end-to-end delivery.
  Zero-row responses are supported by
  [PostgREST's documented limit=0 behavior](https://docs.postgrest.org/en/v11/releases/v10.0.0.html).
- Neither probe runs opportunistic cleanup or writes data. Readiness checks
  still contact the database; use a modest monitor interval (for example 60
  seconds), not browser polling. Hosting-level abuse controls remain necessary.
- Each Supabase auth/REST/RPC operation has a five-second deadline covering
  headers and response-body reading; readiness uses a two-second deadline.
  These are per-operation limits, not a total duration guarantee for a relay
  request containing multiple operations.
- A timeout aborts the outgoing request, returns a recoverable relay error and
  never automatically retries a write. A write might already have committed:
  keep the existing delivery-status check rather than submitting a duplicate.
  An auth-service outage is not reported as invalid phone credentials.

Monitor both liveness and readiness, but keep real pairing/send/revoke acceptance
checks as a separate release gate. Neither endpoint is proof of complete relay
availability. CI and opt-in scheduled retention scripts are prepared separately;
hosted CI verification and live Cron activation remain pending. See the
[CI and retention runbook](../docs/ci-retention-operations-2026-10-21.md).

## Privacy boundary

The camera permission is requested only after the user presses **Scan QR** and
the camera is released when scanning ends, the scanner is closed, or the page
moves to the background. QR frames are decoded locally and are never uploaded.
The decoded result exists only in page memory. When **Send to PC** is chosen,
only an end-to-end encrypted envelope is uploaded. The relay temporarily keeps
that ciphertext until acknowledgement or expiry and cannot derive the URL.

The PWA never requests microphone, location, photo-library, Bluetooth or
local-network access. It has no analytics, advertising or third-party runtime
scripts. The service worker never intercepts application requests and never
caches URLs, relay responses, tokens or cryptographic keys. Pair credentials
are stored only in IndexedDB; the root key is a non-extractable CryptoKey.
Supabase's anonymous device session requests no email, phone number or profile.
Hosting providers may still process standard connection metadata such as IP
addresses under their own infrastructure policies. See
`THIRD_PARTY_NOTICES.md` for the bundled decoder license.
