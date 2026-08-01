# QR Scanner Phone-to-PC PWA

This directory contains the install-optional mobile web companion for Webcam QR
Scanner. It is intentionally isolated from the Python desktop application and
relay service.

## Current scope

The current PWA milestone includes:

- a responsive mobile application shell;
- an installable web manifest and platform icons;
- optional Home Screen installation guidance;
- a minimal service worker that caches only public static branding assets;
- first-party-only runtime resources;
- restrictive security and permissions headers;
- a camera scanner started only by an explicit user action;
- on-device QR decoding with a pinned, locally bundled decoder;
- strict HTTP/HTTPS URL validation and a result confirmation screen;
- WQRS/1 pairing with browser-native P-256, HKDF-SHA-256 and AES-256-GCM;
- non-extractable root-key persistence in IndexedDB;
- end-to-end encrypted **Send to PC** with an authenticated delivery receipt;
- automatic camera cleanup when the scanner closes or the page is hidden;
- a D1-backed relay API that stores only short-lived opaque envelopes and
  refuses messages when the PC receiver is offline;
- automated render, URL-policy, protocol-vector, D1 relay, manifest,
  cache-policy and security-header tests.

**Open on this phone**, browser pairing, and encrypted **Send to PC** are
available through the public beta endpoint. One complete iPhone-to-Windows
pairing and encrypted URL delivery has been verified manually. Broad Android
Chrome and iOS Safari testing plus an independent security review are still
required, so this remains a preview rather than a stable public service.

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
are stored only in IndexedDB; the root key is a non-extractable CryptoKey. See
`THIRD_PARTY_NOTICES.md` for the bundled decoder license.
