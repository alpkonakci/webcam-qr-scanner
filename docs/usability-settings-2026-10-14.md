# TR/EN, connection state and Settings/About preview

Local preview: `0.2.0-beta.8-preview`. Public beta.7 and the production phone
site have not been changed by this work.

## Implemented

- Shared Turkish and English UI catalogues for Windows and the phone site.
  Language is saved per Windows user / browser. QR payloads, URLs, device names,
  protocol values and credentials are not translated.
- Clear actions: connect a phone, remove access, and connect to this PC instead.
  Removing access still requires confirmation; opening a received link still
  defaults to No. The sender's verified receipt is not browser-opening approval.
- Saved pairing and receiver reachability are independent. Authenticated GET
  status requests report the existing server heartbeat lease. Unknown, old,
  hidden-tab and failed checks do not report a confirmed online PC. Offline
  status does not erase saved credentials or send another message.
- Settings/About contains version, official GitHub downloads and language.
  Windows also exposes the existing per-user startup control. Merely opening
  Settings never changes the registry; startup keeps the camera off.
- Desktop children share an expiring, credential-free receiver status file.
  This is a recent-confirmation indicator, not a guarantee of instantaneous
  network reachability. The existing heartbeat cadence is unchanged.

## Verification

- 312 desktop unit/integration tests passed, including real hidden Tk settings,
  language persistence, malformed preferences, explicit startup changes,
  expiring health and Settings child lifecycle.
- 114 web tests passed; production Next build, TypeScript and ESLint passed.
  Tests cover authenticated status GETs, fresh/stale heartbeat, invalid/revoked
  credentials, exact copied QR data and Turkish pending/received labels.
- Real local browser checks at 390x844: both language choices, refresh
  persistence, version/download URL, Back, no horizontal overflow. Settings
  stays visible on narrow screens; no camera permission was granted for these
  checks.
- Desktop production canvas renders were inspected in both languages. Native
  Settings logic was tested using hidden Tk windows; a physical-phone check
  against a future deployment is still needed before publication.

## Local test

The packaged EXE is under `dist/usability-20261014/`. Keep the released beta.7
until this preview is accepted. Exit an already-running QR Scanner before
opening the preview so its single-instance guard does not select the old EXE.
Choose Settings/About -> Turkish, return to the home screen, then check the
pairing/send/remove flow. Do not enable Windows startup from a temporary test
folder unless that folder is intended to remain in place.

Local web preview: `http://127.0.0.1:3110/` (this address is on the PC only).
The published phone site will not show these changes until a separately
authorized deployment. No database migration is required.
