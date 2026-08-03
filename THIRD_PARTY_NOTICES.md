# Third-Party Notices

The Webcam QR Scanner source code is licensed under the MIT License. The
Windows distribution also contains the following third-party components. They
remain subject to their own licenses and are not relicensed under MIT.

## Components included in the Windows package

- **CPython 3.12.13** — Python Software Foundation License
- **NumPy 2.5.1** — BSD 3-Clause License and licenses of bundled components
- **opencv-python 5.0.0.93** — Apache License 2.0 and licenses of bundled
  third-party components
- **Pillow 12.3.0** — HPND License (MIT-CMU)
- **pystray 0.19.5** — GNU Lesser General Public License v3.0
- **six 1.17.0** — MIT License
- **cryptography 49.0.0** — Apache License 2.0 or BSD 3-Clause License
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

The distributable ZIP contains the complete license material copied from the
exact Python environment used to build the executable:

```text
THIRD_PARTY_LICENSES/
|-- AnyIO/
|-- certifi/
|-- cffi/
|-- cryptography/
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
|-- typing_extensions/
`-- websockets/
```

PyInstaller's Bootloader Exception grants permission to embed its compiled
bootloader in, and distribute it with, applications under other licenses. It
does not change the license of the application source code.

## Components included in the PWA

- **qr-scanner 1.4.2** — MIT License; camera lifecycle and on-device QR decoding
- **@types/offscreencanvas 2019.7.3** — MIT License; type declarations used by
  `qr-scanner`

The complete PWA license texts are stored under `pwa/THIRD_PARTY_LICENSES/`.
The decoder is bundled with the first-party application assets and is not
loaded from a CDN at runtime.

This notice is informational and does not replace any included license text.
