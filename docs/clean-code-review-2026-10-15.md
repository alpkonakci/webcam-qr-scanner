# Behavior-preserving code cleanup — 2026-10-15

Scope approved by the user: readable native-control constants and records,
explicit desktop types/names, and simpler phone view/image-read code. This is
not a claim that the entire application has been redesigned or audited.

## Changes

- `accessible_controls.py`: names for Win32 flags/messages; immutable named
  control records replace tuple indexes. The existing control interface and
  native flag values, selection messages, focus cues and timer behavior stay
  unchanged.
- `accessible_desktop.py`: typed phone/settings inputs and callbacks,
  clearer callback names, explicit connection-status branches. Confirmation
  and startup-preference behavior are unchanged.
- `pwa/lib/home-view.ts`: one pure decision module keeps content precedence
  and its accessible heading together. Storage errors remain distinct from
  missing pairings. The camera remains a separate overlay; existing result
  focus grouping is preserved.
- `PwaHome.tsx`: explicit view rendering and one scan-start operation replace
  repeated conditions/state resets. No new state machine or framework added.
- `QrImageView.tsx`: one internal read lifecycle owns busy/error/latest-job
  guards for whole-image and crop reads. Loading, decoding, clipboard and
  disposal still use the existing modules; no generic task framework added.
- Two brittle positive source-code checks were replaced with actual React
  rendering and browser behavior coverage. The negative network/camera/upload
  capability guard is retained.

## Verification

- Python full suite: **318 passed**; includes real Windows controls.
- Web full suite: **123 passed**, production build and runtime source/trace
  gate included. ESLint and TypeScript checks passed.
- Isolated headless Chromium at 390 × 844: direct image decoding, ambiguous
  multiple-QR selection, keyboard crop, paste event, cancellation/reopening,
  Unicode text preservation and no horizontal overflow passed. No user browser
  profile, OS clipboard or camera permission was used. No upload/send request
  or extra tab was observed.
- Cancellation check deliberately holds a real file read of a valid link QR,
  cancels it, displays a new text QR, then releases the old read. The old load
  must not allocate another image URL or replace the new text result.
- Independent read-only review found no production-code blocker. Its test
  findings (source-regex coupling and an initially weak cancellation fixture)
  were addressed and rechecked.

No new production dependency, protocol/schema change, push, merge, deployment
or EXE rebuild was made. Existing release/test EXEs were left untouched. The
physical iPhone/Android Home Screen and spoken screen-reader checks documented
in the previous report remain pending; this refactor does not certify them.

## Re-running local browser QA

1. Generate synthetic fixtures with
   `.venv\Scripts\python.exe pwa\tests\create-image-fixtures.py dist\cleanup-qa-20261015`.
2. Run `npm test` from `pwa`, then start its production build on a localhost
   port (`npm run start -- --hostname 127.0.0.1 --port 3112`).
3. Run `node tests/browser-cleanup-smoke.mjs <playwright-module> <chromium-exe>
   http://127.0.0.1:3112 ../dist/cleanup-qa-20261015` from `pwa`. Browser tools
   are supplied by the workspace runtime, not a production dependency.
