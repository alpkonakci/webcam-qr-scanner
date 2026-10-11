# Third-Party Notices

The Webcam QR Scanner source code is licensed under the MIT License. The
Windows distribution also contains the following third-party components. They
remain subject to their own licenses and are not relicensed under MIT.

## Components included in the Windows package

- **CPython 3.12.14** — Python Software Foundation License
- **Tcl/Tk 8.6.12** — Tcl/Tk permissive license; offline QR creator and
  read-only text result windows via Python's standard-library tkinter
- **SQLite 3.53.1** — public domain; bundled with CPython for the encrypted
  replay ledger. [Upstream copyright statement](https://sqlite.org/copyright.html).
- **NumPy 2.5.1** — BSD 3-Clause License and licenses of bundled components
- **opencv-python 5.0.0.93** — Apache License 2.0 and licenses of bundled
  third-party components
- **Pillow 12.3.0** — HPND License (MIT-CMU)
- **pystray 0.19.5** — GNU Lesser General Public License v3.0 or later
- **six 1.17.0** — MIT License
- **cryptography 50.0.2** — Apache License 2.0 or BSD 3-Clause License
- **comtypes 1.4.17** — MIT License
- **DXcam 0.3.0** — MIT License; DXGI desktop capture
- **cffi 2.1.0** — MIT No Attribution License
- **HTTPX 0.28.1** — BSD 3-Clause License
- **HTTPCore 1.0.9** — BSD 3-Clause License
- **AnyIO 4.14.2** — MIT License
- **certifi 2026.7.22** — Mozilla Public License 2.0
- **idna 3.18** — BSD 3-Clause License
- **h11 0.16.0** — MIT License
- **typing_extensions 4.16.0** — Python Software Foundation License 2.0
- **PyInstaller 6.21.0 bootloader and run-time hooks** — GPL-2.0-or-later with
  the PyInstaller Bootloader Exception, plus Apache-2.0-licensed run-time hooks

- **websockets 16.1.1** — BSD 3-Clause License
- **Click 8.4.2** — BSD 3-Clause License; indirect runtime import
- **Colorama 0.4.6** — BSD 3-Clause License; indirect Windows console helper
- **pyinstaller-hooks-contrib 2026.6 run-time hooks** — Apache License 2.0;
  build-time hooks retain their separate GPL license and are not runtime code

The packaging inventory is generated from PyInstaller's actual analysis and
fails if a site-packages input cannot be attributed to a licensed distribution.
`THIRD_PARTY_LICENSES/INVENTORY_LICENSES` contains each included distribution's
complete license tree (including the above indirect components), alongside
`DEPENDENCY_INVENTORY.json`. The earlier named license directories are retained.

## Source access and rebuilding the single-file executable

The updated packaging recipe supplies `APPLICATION_SOURCE.zip` and
`SOURCE_REVISION.txt`, plus complete pystray and certifi source archives under
`THIRD_PARTY_LICENSES/SOURCES`. Their immutable upstream identities and SHA-256
checksums are in that directory's `manifest.json`. Sources are provided under
their own LGPL/MPL terms, not relicensed as MIT. The full MPL 2.0 text is included.
See the accompanying `REBUILDING.md` for modifying the library and rebuilding
an interface-compatible Windows executable. Such modifications and reverse
engineering to debug them are not restricted by this project.

The updated Windows recipe excludes the separate OpenCV FFmpeg video plugin,
which this local-camera/image QR application does not use. MSMF/DirectShow,
OpenCV image decoding and the native OpenCV module remain. Upstream OpenCV
notices are retained in full even where they describe components not shipped.
NumPy's upstream notice includes OpenBLAS/LAPACK and the GCC runtime library
exception; those complete texts are retained, not replaced with a MIT label.

The distributable ZIP contains the complete license material copied from the
exact Python environment used to build the executable:

```text
THIRD_PARTY_LICENSES/
|-- AnyIO/
|-- certifi/
|-- cffi/
|-- cryptography/
|-- comtypes/
|-- DXcam/
|-- h11/
|-- httpcore/
|-- HTTPX/
|-- idna/
|-- NumPy/
|-- OpenCV/
|-- Pillow/
|-- PyInstaller/
|-- Python/
|-- pystray/
|-- six/
|-- Tcl-Tk/
|-- typing_extensions/
`-- websockets/
```

PyInstaller's Bootloader Exception grants permission to embed its compiled
bootloader in, and distribute it with, applications under other licenses. It
does not change the license of the application source code.

## Components included in the PWA

- **Next.js 16.4.0** — MIT License; PWA rendering and Vercel API routes
- **React 19.2.8** — MIT License; browser user interface
- **React DOM 19.2.8** — MIT License; browser rendering
- **Drizzle ORM 0.45.2** — Apache License 2.0; versioned relay schema tooling
- **qr-scanner 1.4.2** — MIT License; camera lifecycle and on-device QR decoding
- **@types/offscreencanvas 2019.7.3** — MIT License; type declarations used by
  `qr-scanner`

The camera-decoder license texts are stored under
`pwa/THIRD_PARTY_LICENSES/`. The exact PWA and server dependency graph is pinned
in `pwa/package-lock.json`; npm package license metadata remains part of the
Vercel build input. The decoder is bundled with the first-party application
assets and is not loaded from a CDN at runtime.

Development-only glob calls use **tinyglobby 0.2.17** (MIT) via the private
`pwa/vendor/build-glob` compatibility adapter (project MIT license). Its
dependencies are fdir (MIT) and picomatch (MIT). These build tools are excluded
from the browser/relay runtime by the runtime boundary checks. Upstream:
https://github.com/SuperchupuDev/tinyglobby.

Vercel and Supabase are managed infrastructure services, not components
bundled into the Windows executable or browser JavaScript. Their service terms
and privacy policies apply to the deployment operator separately from this
project's MIT source license.

This notice is informational and does not replace any included license text.
