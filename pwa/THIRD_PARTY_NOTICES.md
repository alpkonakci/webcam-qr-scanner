# Third-party notices

The Phone-to-PC PWA bundles the following third-party software for on-device QR
decoding. No code is loaded from a CDN at runtime.

The updated build also generates `public/licenses/THIRD_PARTY_NOTICES.txt`
from the exact installed Next.js, React, React DOM and qr-scanner licenses,
plus the separate notices of Next's compiled subcomponents. It is linked from
the home page and served as a static file. The list below is a decoder-specific
summary, not a statement that all browser software belongs to those two packages.

## qr-scanner 1.4.2

- Project: https://github.com/nimiq/qr-scanner
- License: MIT
- Purpose: camera lifecycle and on-device QR code decoding
- License text: `THIRD_PARTY_LICENSES/qr-scanner/LICENSE`

## @types/offscreencanvas 2019.7.3

- Project: https://github.com/DefinitelyTyped/DefinitelyTyped
- License: MIT
- Purpose: type declarations used by `qr-scanner`
- License text: `THIRD_PARTY_LICENSES/types-offscreencanvas/LICENSE`
