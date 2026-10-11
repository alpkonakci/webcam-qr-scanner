# QR creation and mobile screenshots — local preview, 2026-10-10

## Implemented locally

- Desktop control center and tray: **Create QR**.
- Link / short text, live preview, lossless PNG export and explicit image copy.
- Encoding happens on the PC. No network request, file upload or automatic link opening.
- Maximum 600 UTF-8 bytes to keep this first version readable. Turkish text,
  emoji and line breaks are supported. Link mode allows complete HTTP/HTTPS
  addresses without embedded credentials.
- Video, GIF, PDF and other large files use their existing sharing URL. The
  app does not host files, create public access or embed video bytes in a QR.
- Desktop non-link scans show a selectable, read-only **Text QR** window.
- Mobile source has a separate escaped, read-only text result and user-triggered
  copy with a manual-selection fallback. Text is never sent through the relay.
- Mobile source now also has **Read from image**: a user-triggered file chooser
  or clipboard paste, automatic scanning and pointer/touch crop as a fallback.
  Selected images are never uploaded or saved by the app.
- Existing link confirmation, encrypted URL delivery, revocation and replay
  controls are unchanged.

The mobile web changes were deployed to `https://qrwebcam.vercel.app` on
2026-10-10 after explicit user approval (details below). This is not a new
GitHub release or desktop package. The published beta.4 EXE and ZIP remain unchanged. The separate candidate is under
`dist/qr-create-preview-20261010/`.

## Mobile screenshot research

### Implemented locally: choose an image

User flow: take a screenshot normally → open the QR Scanner site → choose
**Read from image** → select or paste that screenshot → automatically show the decoded link or text →
explicitly open/copy/send. If no QR is found, explain how to crop tightly or
use a sharper image. For multiple detected QR codes, select one QR area and
read that selection. Do not claim that enlarging a blurred QR restores lost
information.

Our installed qr-scanner library already supports `scanImage(File/Blob, ...)`.
The implementation uses no upload or camera permission. The file chooser is
user-triggered and does not request access to the whole gallery. Sources:
[qr-scanner upstream API](https://github.com/nimiq/qr-scanner),
[browser File API](https://developer.mozilla.org/en-US/docs/Web/API/File_API/Using_files_from_web_applications).

Implemented safety boundaries:

- PNG/JPEG/WebP raster input; exclude SVG, animated GIF and arbitrary documents
  in the first version. Inspect signatures and dimensions before image loading;
  reject animated PNG/WebP as well. MIME and filename are not trusted.
- Up to 10 MB, 20 million pixels and 8192 pixels per side. Loading/scanning each
  have a 12-second deadline; abort/timeout/unmount revoke blob URLs and terminate
  owned decoding workers. Decoding canvases are capped at 1600 pixels per side.
- Selection uses original image coordinates, not thumbnail pixels. After the
  first detected code is masked, another decode checks for a second code; if
  detected, the user must narrow their selection. This is not a guarantee that
  every blurred/partially hidden code in an image can be detected.
- Cancel/no QR/corrupt image/unsupported format/over-limit image leave pairings
  unchanged and open/send nothing.
- Reuse the current URL security policy and text-only view.
- Results reuse the camera's pairing/URL/text routing. No automatic link opening
  or URL sending is added. Repeat scans return to the same image-reader mode.
- CSP permits local blob image previews, not arbitrary remote image hosts.

### Clipboard image input (local preview)

- Choose image remains available beside Paste image; Ctrl+V / Cmd+V uses the
  user-initiated paste event while the image reader is open.
- No clipboard polling, text/HTML parsing or fetching copied image URLs.
  Pasted blobs use the same byte, size, dimension and crop validation as files.
- Browser clipboard permission denial or missing support gives keyboard/file
  fallback guidance. Pending reads are cancelled on exit and time-bounded.
- 96 PWA tests passed. Chromium's actual ClipboardItem read/write and keyboard
  paste passed with a synthetic PNG; copied URL content was rejected without
  network access. Mobile-width screenshot: `paste-390.png` in the QA directory.
- Native iOS/Android clipboard behavior still requires real-device testing;
  browser permissions may show a paste prompt. Live deployment details below.

### Automatic image scan (local preview)

Selected or pasted images are now scanned immediately with the existing
multi-code check. One decoded QR goes to the shared result view, never directly
opens a URL or sends to a PC. Multiple detectable QR codes, no QR or an unreadable
image keep the local preview and expose manual crop / another-image options.
Cancellation and stale-result checks cover both automatic and manual scans.

Real iPhone Safari and Samsung S24 FE native file pickers, rotations and
cross-network Send to PC still require device testing. The feature is implemented
and tested locally and in the production browser; real-device tests for this
new image/clipboard feature remain pending.

### Production deployment — 2026-10-10

- User approved publishing the phone-site image/paste feature.
- Source commit: `b3d0fa92a4aaf091f118a2b282dd4e3e45a8ac40` on
  `codex/vercel-supabase`; main and desktop changes were not included.
- Preview deployment: `BqBmHaTs54YqNirER98ZPeP4hjwM` (Ready).
- Rebuilt using Production environment, deployment:
  `5KJriTLD82NYwntsSKHPfY5oierp` (Ready), alias `qrwebcam.vercel.app`.
- Live browser verification: image action, choose and paste buttons; a synthetic
  single QR automatically decoded to `https://example.com/image-test`;
  a multi-QR image required a crop; pasting a synthetic PNG automatically decoded
  the same URL. No open/send action was taken and pairings were not modified.
- Homepage and `/healthz` both returned HTTP 200 after publication; health stayed
  `wqrs/1`, `supabase-realtime`. CSP allowed local blob previews.
- 96 PWA tests, production build and full ESLint passed before rollout;
  `npm audit --omit=dev` returned zero vulnerabilities. The previously reported
  8 high dev-tool warnings were not claimed to be fixed.
- Live proof screenshot: `dist/mobile-image-qa-20261010/live-image-reader-20261010.png`.
- Existing beta.4 EXE/ZIP hashes were checked again and remain unchanged.

### Light-on-dark image QR hotfix — 2026-10-10

- User approved fixing and publishing the poster-image decoding failure.
- Root cause: our owned qr-scanner worker retained its default original-only
  polarity. The supplied poster uses a light QR on a dark background.
- Owned workers now explicitly use both polarities. Native BarcodeDetector
  retries a locally inverted canvas only after a no-QR result; the same logic
  also checks for a second code. Cancellation, deadlines and image limits remain.
- Source: `219d7bdb31b1f5384f45694e54be866010e3aed8`, branch
  `codex/vercel-supabase`. No main, database or Windows package changes.
- Preview `GqqbYpMw38PwNQEL3FMyGysGCx46` and Production rebuild
  `FW7gsTRxEmDq6kx3zgKaahJK1egf` both reached Ready. The Production alias
  is `qrwebcam.vercel.app`.
- All 100 PWA tests, production build and full ESLint passed. Browser smoke
  covered normal/inverted single codes, mixed/all-inverted multiple codes,
  clipboard input, crop fallback and the user's actual poster.
- The actual poster decoded automatically both locally and on the live site
  to `https://www.canvaqr.com/RGUogyLfS4`. No link was opened or sent to a PC;
  the poster was processed on-device and was not committed to the repository.
- `/healthz` returned HTTP 200 with `wqrs/1`, `supabase-realtime` after rollout.
- Live proof: `dist/mobile-image-qa-20261010/live-poster-result-20261010.png`.
- Real-phone retest of this hotfix remains pending. This change does not resolve
  the previously reported 8 development-tool security warnings.

### Direct capture of other apps is a separate native-app feature

The present mobile web app cannot offer reliable cross-app screen capture.
MDN's current compatibility data marks `getDisplayMedia` unsupported for
Chrome Android and iOS Safari (also Firefox Android). Permission must be
requested each time where the web API is available; it is not a silent,
persistent screen-access grant.
[MDN compatibility data](https://github.com/mdn/browser-compat-data/blob/main/api/MediaDevices.json),
[getDisplayMedia API](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia).

A native Android app could use MediaProjection, requiring consent for each
session and appropriate foreground-service lifecycle/cleanup. This would add
permissions, packaging, maintenance and real-device testing beyond the current
web companion. [Android MediaProjection](https://developer.android.com/media/grow/media-projection).

Protected screens can intentionally block screenshots or projection. Do not
attempt to bypass these protections; explain the limitation and offer a normal
sharing link instead. [Android secure activities](https://developer.android.com/security/fraud-prevention/activities).

## Verification

- 285 desktop unit/integration tests passed in the Windows-capable test run.
- 90 PWA tests passed, including image limits/cancellation/deadline/ambiguity, text escaping/copy fallback, unsafe URL
  rejection, pairing removal and late authenticated delivery receipts.
- Next production build, Worker/Vite build and TypeScript check passed.
- Runtime boundary: 24 runtime sources and 5 Next traces checked.
- Image feature production build: 28 runtime sources and 5 Next traces checked.
- Headless Chromium mobile-viewport smoke test passed on the production server:
  PNG/JPEG/WebP; repeat selection; Unicode multiline text; no QR; multiple QR;
  pointer crop; forged SVG named PNG; Back; no horizontal overflow; no POST,
  automatic navigation or page errors. Synthetic fixtures only, no user photos.
  Automatic selection/paste scanning and manual multi-code crop fallback were
  rechecked after removing the mandatory selection step; all 96 PWA tests and
  the production build passed again.
  Screenshots: `dist/mobile-image-qa-20261010/home-390.png` and `crop-390.png`.
- Standalone candidate `--self-test` passed. Packaged Windows EXE visual QA
  repeated on 2026-10-10 using Computer Use (not just source previews):
  - Home menu: all four cards fit; correct app icon; maximize disabled.
  - Creator: link/text selection, input, QR preview and action row fit without
    clipping in the tested Windows display configuration.
  - Link PNG saved through the native file dialog; decoded back to the exact
    test URL (`https://example.com/qr-visual-test`). RGB PNG, 481 × 481 pixels.
  - Turkish characters, emoji and two lines of text saved through the same
    dialog; exact decoded round trip. RGB PNG, 495 × 495 pixels.
  - Copy QR displayed its success state. Clipboard writes used the normal
    Windows process context; sandbox-denied access is not an app defect.
  - Cancelling Save kept the preview and input intact. Invalid link and empty
    input showed guidance and disabled both export actions.
  - Back closed the isolated creator process cleanly.
  - Published beta.4 EXE and ZIP SHA-256 hashes remain unchanged.

This visual pass did not repeat real-phone pairing, camera capture or every
Windows DPI/display size. On 2026-10-11 the user confirmed that selecting the
supplied poster and pasting another QR both opened successfully on the phone.
This targeted acceptance does not complete a full iPhone/Android device matrix.

No new npm or Python package was installed for this feature. tkinter uses
the bundled Tcl/Tk runtime; its license is now included by the packaging script.
