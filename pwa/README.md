# QR Scanner Phone-to-PC PWA

This directory contains the install-free mobile web companion for Webcam QR
Scanner and the Vercel-hosted relay API. The WQRS/1 cryptographic contract stays
shared with the Python desktop application while deployment-specific code stays
inside this directory.

> **Migration status:** `codex/vercel-supabase` contains the tested first
> Vercel + Supabase migration slice. A protected Vercel Preview deployment is
> ready, but it has not passed real-device acceptance tests. The existing
> Sites/Cloudflare beta remains live; this branch is not the production endpoint.

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
- short-lived browser-open and phone-cancel signals that dismiss the desktop
  QR without granting pairing approval;
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

**Open link in new tab**, browser pairing, and encrypted **Send to PC** remain
available through the existing public beta endpoint. The Vercel + Supabase
replacement is locally built and automatically tested, with an access-protected
Preview deployment; it is not the production endpoint yet.
Broad Android Chrome and iOS Safari testing plus an independent security review
are still required, so this remains a preview rather than a stable service.

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
