# Webcam QR Scanner

**English** | [Türkçe](README.tr.md)

A fast and secure Windows desktop application that scans QR codes with a
computer camera and opens valid web links in the default browser.

## Features

- Live camera preview with a modern turquoise interface
- A visible guide that is also the real QR analysis area
- Single and multiple QR-code detection
- Automatic opening of valid HTTP/HTTPS links
- Automatic shutdown after the first successful scan
- Duplicate-scan prevention
- 1920×1080 at 30 FPS target with automatic 1280×720 fallback
- Non-blocking background analysis that always prioritizes the newest frame
- Periodic high-detail detection for small or distant codes
- Additional processing for QR codes displayed on phone screens
- Developer FPS overlay available with `--show-fps`
- Safe exit with `Esc` or the window close button
- Terminal-free standalone Windows executable

## Download and use

Download `Webcam-QR-Scanner-v0.1.0-windows-x64.zip` from the latest GitHub
Release, extract it, and double-click `QR-Scanner.exe`. No separate Python or
OpenCV installation is required.

1. Allow camera access if Windows asks for permission.
2. Place the complete QR code inside the turquoise frame.
3. A valid web link opens in the default browser.
4. The scanner closes after the first successful scan.

The first launch can take a few seconds longer because the single-file package
needs to prepare its bundled files. Windows SmartScreen may warn about unsigned
executables downloaded from the internet.

## Scanning from a phone screen

- Avoid maximum screen brightness. Reflections and overexposure can make the QR
  code difficult for the camera to detect.
- Medium brightness generally produces better results.
- Keep the phone as straight as possible and reduce reflections by slightly
  changing its angle.
- Make sure the complete QR code is inside the scan frame. Start at a distance
  of approximately 15–30 cm.
- If a moiré pattern appears, move the phone a few centimetres closer or farther.

## Performance

Camera capture and QR decoding run independently. The worker analyzes only the
newest available frame instead of building a queue, so QR processing does not
freeze the preview. Analysis is restricted to the turquoise guide area.

At startup, the application measures the 1920×1080, 30 FPS camera stream. If
that resolution is unsupported or falls below 24 FPS, it attempts to switch to
1280×720 at 30 FPS.

### Local benchmark

These measurements were recorded on the development computer and are not a
performance guarantee. The camera, processor, Windows driver, and lighting can
all affect the result.

- Platform: Windows with the OpenCV Media Foundation camera backend
- Camera target: 1920×1080 at 30 FPS
- Scope: camera capture, background QR analysis, and interface rendering
- Measured full-pipeline rate: approximately 30.1 FPS
- Measured fast QR-analysis capacity: approximately 48.7 FPS

The FPS counter is hidden by default. Enable it for development:

```powershell
.\.venv\Scripts\python.exe app.py --show-fps
```

Normal performance is shown in turquoise and a value below 24 FPS is shown in
amber. Green is reserved for successful QR detection.

## Run from source

Python 3.10 or newer is required:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Useful options:

```powershell
# Use another camera
.\.venv\Scripts\python.exe app.py --camera 1

# Do not open links automatically
.\.venv\Scripts\python.exe app.py --no-open

# Keep scanning after the first QR code
.\.venv\Scripts\python.exe app.py --keep-open

# Display the developer FPS overlay
.\.venv\Scripts\python.exe app.py --show-fps
```

`QR Scanner.vbs` starts the source version without a terminal. The
`start_qr_scanner.bat` launcher keeps the terminal visible for diagnostics.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe app.py --self-test
```

The self-test verifies OpenCV imports and QR decoding without opening a camera.

## Build the Windows executable

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\build_exe.bat
```

The build produces the terminal-free executable and a distributable ZIP:

```text
dist\Webcam-QR-Scanner-v0.1.0-windows-x64.zip
```

The ZIP contains `QR-Scanner.exe`, the project MIT license, the third-party
notice, and the complete license material for bundled dependencies. A
`SHA256SUMS.txt` file is also generated for integrity verification.

## Project structure

- `app.py`: application flow and command-line options
- `camera.py`: camera negotiation, Full HD measurement, and 720p fallback
- `qr_reader.py`: fast and thorough QR decoding
- `scan_worker.py`: newest-frame-only background worker
- `scan_geometry.py`: real scan area and coordinate transformations
- `ui.py`: interface, animated scan line, and result presentation
- `links.py`: safe URL classification and browser integration
- `performance.py`: optional FPS measurement
- `tests/`: automated behavior, camera-selection, and QR-reader tests

## Security

Only explicit, valid `http://` and `https://` URLs are opened automatically.
Payloads using schemes such as `javascript:` or `file:` are never executed. A
QR code held in front of the camera does not continuously open new tabs.

## Roadmap

### v0.1 — Windows desktop release

- [ ] Publish the source code on GitHub
- [x] Build a standalone, terminal-free Windows executable
- [ ] Publish a `v0.1.0` GitHub Release
- [ ] Add a screenshot, usage GIF, and release notes

### v0.1.1 — Scan QR codes displayed on the computer screen

Planned as an opt-in feature. It will scan the active display or a user-selected
area without permanently storing screenshots. Duplicate protection, HTTP/HTTPS
validation, multi-monitor support, and a confirmation option will be preserved.

### v0.2 — Phone-to-PC bridge

Planned secure pairing between a phone and the computer. A QR code scanned with
the phone will be sent over the local network and opened in the computer's
default browser after validation.

## License

Copyright © 2026 [alpkonakci](https://github.com/alpkonakci).

This project is licensed under the [MIT License](LICENSE).
Bundled dependency licenses are documented in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
