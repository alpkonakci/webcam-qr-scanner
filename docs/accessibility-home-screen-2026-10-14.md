# Accessibility and Home Screen preview — 2026-10-14

Version: `0.2.0-beta.8-preview.2`. Local test package only; no GitHub release or production deployment was made for this change.

## Implemented

- Windows main menu, paired-phone management and settings now use actual standard Windows buttons, list/choice controls and a startup toggle. They expose native UI Automation roles and names, keyboard focus, Tab/Shift+Tab navigation and Enter activation. Existing removal, exit and close-choice confirmations remain in place.
- A shared control-window module owns native resources and dispatch. Domain decisions stay in the existing home/pairing modules. Opening settings does not change the Windows startup preference. The new control layer adds no Python dependency.
- Phone views have labelled headings and focus moves when the view changes. The camera is a labelled modal with background interaction disabled, keyboard focus containment and Escape/Close. Image cropping additionally has labelled percentage fields for keyboard users.
- A collapsed, translated Home Screen guide provides official Safari/Chrome steps, detects installed display mode and explains separate pairing storage. Storage failures are not described as an empty pairing.
- No pairing key is exported, placed in a URL or copied between browser stores. A missing pairing inside an installed app is recovered by normal pairing from inside that app.

## Completed checks

- Python: **318 tests passed**, including six tests using real Windows controls (visible focus cues, Tab/Enter, disabled controls, exit cancellation, removal confirmation, unchanged startup on open, explicit toggle and exact Unicode choice values).
- Web: **120 tests passed**, including the production build, TypeScript and runtime-boundary checks. ESLint passed.
- Storage tests use the production pair store with actual IndexedDB-style transactions: a reopened store retains a non-exportable key; an isolated store has no pairing; returning to the original store retains its pairing. The IndexedDB test implementation is a development-only dependency. This models storage boundaries; it does not certify a particular phone/browser installation behavior.
- Browser UI: Tab/Enter into image reading, labelled crop fields, enabled read action after keyboard crop, Escape back to the focused home heading, Turkish language and expanded guide. At 390 × 844 CSS pixels, no horizontal overflow was observed.
- Native UI inspection: real Windows UI Automation controls and names, focus movement, disabled maximize and readable startup state. A temporary UTF-16 buffer lifetime issue and a hidden-focus-cue flag found during inspection were fixed and regression-tested.
- Frozen EXE: self-test passed; distribution archive check passed (1,135 entries); accessible modules and the Turkish catalogue are bundled.

## Still requires real-device / assistive-technology validation

Do not mark the following as passed based on desktop emulation or storage unit tests.

1. In iPhone Safari, use the saved pairing and send a QR to the running PC.
2. Follow Share → Add to Home Screen (enable Open as Web App if offered), then open the new icon.
3. Check the PC name in that app. If no pairing is present, pair once **from inside that app** using its scanner. Do not copy keys or assume Safari's pairing transferred.
4. Send a QR, verify the actual PC confirmation, close/reopen the installed app and send again.
5. Return to the original Safari window and verify its original pairing still works.
6. Repeat with Android Chrome's Add to Home screen / Install flow. Record phone model, OS/browser versions and whether the pairing was shared or separate; either outcome must have a usable recovery path.
7. With Narrator/VoiceOver/TalkBack, check names, control roles, state announcements, reading order and safe cancellation. UI Automation/ARIA inspection is not a substitute for spoken screen-reader testing.

The accessibility conversion covers the agreed three desktop control screens and phone views. It is not a claim that every camera/selection canvas in the desktop application is fully screen-reader operable.

## Primary references

- [Apple: turn a website into an iPhone app](https://support.apple.com/en-lamr/guide/iphone/iphea86e5236/ios)
- [Google: use web apps on Android](https://support.google.com/chrome/answer/9658361?co=GENIE.Platform%3DAndroid&hl=en)
- [WebKit 17.2: Home Screen app storage behavior](https://webkit.org/blog/14787/webkit-features-in-safari-17-2/) — cookies may be copied at installation; other local storage is not copied by that mechanism.
- [Microsoft: UI Automation support for standard controls](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-controlsupport)

Visual proof: `accessibility-20261014/home-screen-guide-mobile-tr.png` (desktop browser at phone-sized viewport, not a physical iPhone).
