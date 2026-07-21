# Third-Party Notices

The Webcam QR Scanner source code is licensed under the MIT License. The
Windows distribution also contains the following third-party components. They
remain subject to their own licenses and are not relicensed under MIT.

## Components included in the Windows package

- **CPython 3.12.13** — Python Software Foundation License
- **NumPy 2.5.1** — BSD 3-Clause License and licenses of bundled components
- **opencv-python 5.0.0.93** — Apache License 2.0 and licenses of bundled
  third-party components
- **PyInstaller 6.21.0 bootloader and run-time hooks** — GPL-2.0-or-later with
  the PyInstaller Bootloader Exception, plus Apache-2.0-licensed run-time hooks

The distributable ZIP contains the complete license material copied from the
exact Python environment used to build the executable:

```text
THIRD_PARTY_LICENSES/
├── NumPy/
├── OpenCV/
├── PyInstaller/
└── Python/
```

PyInstaller's Bootloader Exception grants permission to embed its compiled
bootloader in, and distribute it with, applications under other licenses. It
does not change the license of the application source code.

This notice is informational and does not replace any included license text.
