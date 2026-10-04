# Intentional QR rescans and desktop cursor fixes

These are post-beta.3 fixes. Existing GitHub release assets/tags are unchanged.

## Behavior

- After verified receipt, **Scan another QR** retires only that PC/URL's completed
  attempt. Scanning the same code again creates a fresh encrypted message ID.
- Double taps on one result still share one attempt. Pending, lost-response and
  expired-receipt cases cannot be unlocked by rescanning. Receipt watching stays
  GET-only; desktop replay persistence and relay replay tombstones are unchanged.
- Desktop menus, pairing/recovery windows, camera view and monitor picker use
  the Windows system arrow. Screen-region selection keeps its crosshair.
- Cursor subclassing is limited to this process's current UI thread and both
  OpenCV parent/image windows. Resize/title-bar cursors remain native; subclass
  callbacks are retained for process lifetime and detached on window destruction.

## Verification

- Desktop: 262 unittest cases pass.
- PWA: 59 tests pass; Next production build, TypeScript and ESLint pass.
- Native Windows smoke check passes against real hidden OpenCV windows: image
  cursor arrow, independent region-selection crosshair, destroy/reopen.
- Preview EXE's `--self-test` passes.
- Gitleaks checks of the tracked diff and built client assets pass.

Local test executable (not a new GitHub release):

`dist/rescan-cursor-preview-20261004/QR-Scanner.exe`

SHA-256: `DA3A07FB6F95AE25309443C4C2BF14201155C94545F0444EC4B0BEC1899290ED`

This preview retains beta.3 version metadata; the distinct preview directory
identifies it. Exit the old tray process before opening it, otherwise the single
instance guard routes requests to the already-running old executable.

Physical acceptance: refresh the phone website, send a QR and wait for
**Received by PC**, select **Scan another QR**, scan that same QR, send again and
verify a second PC confirmation. Check arrow cursors in the desktop menus and
the retained crosshair in screen-region selection.
