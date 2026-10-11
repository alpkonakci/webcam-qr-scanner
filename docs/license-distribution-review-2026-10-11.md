# License distribution review — 2026-10-11

Scope: read-only review of the published Windows v0.2.0-beta.6 package and
current packaging instructions. This is a technical checklist, not a legal
opinion or a declaration that every transitive component is fully compliant.

## Project licensing decision

The owner's intent is a useful application that everyone can use, without a
commercial objective for the owner. Keep the existing MIT license. MIT permits
free use, modification and redistribution, including commercial use by others;
it does not require the owner to sell anything. No license text was changed.

Reference: https://opensource.org/license/mit

## Verified

- Project LICENSE: MIT, Copyright (c) 2026 alpkonakci.
- Extracted beta.6 LICENSE.txt is byte-identical to the project LICENSE.
- Extracted beta.6 THIRD_PARTY_NOTICES.md is byte-identical to the project notice.
- THIRD_PARTY_LICENSES contains 20 component directories and 40 files, none empty.
- pystray 0.19.5 metadata declares LGPLv3; its GPL and LGPL license texts are
  included in the Windows package as COPYING and COPYING.LGPL.
- Application source, pinned direct requirements, and a PyInstaller build
  script exist in the project. The PyInstaller command bundles pystray in a
  one-file executable, so substituting the installed Python package at runtime
  is not an established replacement mechanism for the distributed EXE.

## Open validation before stable-release sign-off

The Windows ZIP's pystray directory currently contains only license texts,
not an upstream source archive. The project notice does not yet give a
release-specific source acquisition and modified-library rebuild procedure.
General application source/build instructions exist, but a complete source
access and recombination path has not been demonstrated by this review.

Review the distribution against LGPLv3 section 4 and the incorporated GPLv3
source-conveyance provisions. A concrete technical follow-up is to provide
the exact upstream source for the bundled pystray version, tie the application
source/build instructions to the immutable release tag, and actually rebuild
with an interface-compatible modified library. Copying license texts alone
is not evidence that this remaining requirement is satisfied.

Reference: https://github.com/moses-palmer/pystray/blob/v0.19.5/COPYING.LGPL

Other bundled subcomponents, including native libraries' third-party notices,
still require a complete inventory-to-obligation review. Presence and counts
of license files do not establish that all distribution obligations are met.

## Changes in this review

Only this review record was added. Existing MIT licensing, application source,
published tag/assets, deployed website and local executable were not changed.

## Follow-up implementation and verification

The preceding paragraphs record the original beta.6 check, not the updated
candidate. Following the owner's request to complete the identified gaps:

- Complete pystray v0.19.5 source at upstream commit
  `1907f8681d6d421517c63d94f425f9cdd74d0034` and certifi 2026.7.22 sdist
  are included with pinned SHA-256 manifests. All 13 pystray Python files
  and 6 certifi Python/certificate files match the installed originals
  (Python line endings normalized for this comparison).
- The packaging recipe now includes the exact committed application source,
  its revision identity, LGPL modification/recombination instructions and
  complete MPL text. It does not impose additional reverse-engineering or
  library-modification restrictions.
- Actual PyInstaller input inventory covers 21 Python distributions. Click,
  Colorama and contributed run-time hook notices, missing from the former
  direct-dependency summary, are now included automatically. Unknown
  site-packages inputs or absent/empty license material fail the packaging gate.
- The Windows application does not use FFmpeg file/network video decoding.
  The new recipe omits only its optional DLL. OpenCV, native camera backends
  and QR/image decoding remain. Frozen-archive checks prove FFmpeg is absent.
- A separate pystray source copy was modified with a harmless marker while
  retaining its LGPL notices. The resulting one-file EXE actually imports
  that modified code: a test-only runtime hook asserts the marker at startup.
  Its QR self-test completed with exit code 0. The normal EXE excludes the
  test marker/hook and its QR self-test also passed.
- 292 desktop tests and 106 PWA tests passed; Next build, typecheck and ESLint
  passed. The PWA generates a public full license-notices file, including
  installed browser dependencies and Next's compiled-component notices.

Normal candidate EXE SHA-256:
`9A8A01F84DB281EC78454C8A214DB042654E90FA93C5887A3C2EB7B63D0C5897`.
Modified-library validation EXE SHA-256:
`492FBDA025E5582D8B7B630218FC7567E2AC4E1194857C346546F468CA170592`.

These checks resolve the concrete source/rebuild and notice omissions
identified here. They are not an independent legal opinion, nor a fresh
full physical-device acceptance test. The original beta.6 tag, public assets
and Production website are not modified by this local preparation.
