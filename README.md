# Webcam QR Scanner

**English** | [Türkçe](README.tr.md)

A fast and secure Windows desktop application that scans QR codes with a
computer camera or directly from the screen.

![Webcam QR Scanner interface](docs/assets/webcam-qr-scanner.png)

## Demo

The demo scans a QR code containing this public repository URL, opens it in the
default browser, and closes the scanner automatically.

![Webcam QR Scanner usage demo](docs/assets/webcam-qr-scanner-demo.gif)

> **Development status:** The latest stable GitHub release is `v0.1.1`. The
> current source also contains the `v0.2.0-dev` desktop lifecycle foundation
> and an isolated localhost Phone-to-PC transport prototype. Its short-lived,
> single-use encrypted pairing flow now works through the local relay. The
> user-facing pairing QR, tray integration, internet relay, and mobile PWA are
> not functional yet and are not presented as release-ready features.

## Features

- Live camera preview with a modern turquoise interface
- A visible guide that is also the real QR analysis area
- Separate, one-shot QR scanning across all connected screens
- Link confirmation showing the destination hostname for screen scans
- Click-to-select screen overlay when different QR codes are found
- Single and multiple QR-code detection
- Automatic opening of valid HTTP/HTTPS links
- Automatic camera-view shutdown after the first successful scan
- Duplicate-scan prevention
- 1920×1080 at 30 FPS target with automatic 1280×720 fallback
- Non-blocking background analysis that always prioritizes the newest frame
- Periodic high-detail detection for small or distant codes
- Additional processing for QR codes displayed on phone screens
- Developer FPS overlay available with `--show-fps`
- `Esc` or the window close button closes only the camera view
- Optional background controller with system-tray camera and screen actions
- Confirmed full exit with `Ctrl+Q` or **Exit QR Scanner** in the tray
- Terminal-free standalone Windows executable

## Download and use

Download `Webcam-QR-Scanner-v0.1.1-windows-x64.zip` from the latest GitHub
Release and extract it. No separate Python or OpenCV installation is required.

### Scan with the camera

Double-click `QR-Scanner.exe`:

1. Allow camera access if Windows asks for permission.
2. Place the complete QR code inside the turquoise frame.
3. A valid web link opens in the default browser.
4. In stable `v0.1.1`, the scanner closes after the first successful scan.

### Scan a QR code already displayed on the computer

Keep exactly one QR code clearly visible and double-click `Scan Screen.vbs`.

> **Important:** The QR code must be fully visible when `Scan Screen.vbs` runs.
> A QR code hidden behind another window, inside a minimized window, or on an
> inactive browser tab cannot be scanned. The application scans only what is
> currently visible on the displays, not background window contents.

1. The application captures all connected displays once.
2. The image stays in memory and is never saved.
3. If the QR contains a valid HTTP/HTTPS link, a confirmation dialog shows the
   destination hostname and full address.
4. Select **Yes** to open it or **No** to cancel.

If different QR codes are detected at the same time, nothing is opened. Hide
all but one and run `Scan Screen.vbs` again. The screen is not monitored
continuously.

The first launch can take a few seconds longer because the single-file package
needs to prepare its bundled files. Windows SmartScreen may warn about unsigned
executables downloaded from the internet.

### Current development build: background behavior

The current source and locally generated `v0.2.0-dev` package still distribute
one `QR-Scanner.exe`, but the executable starts separate internal modes:

- A lightweight controller stays visible in the Windows system tray.
- The camera opens only after a user action and runs in a separate process.
- `Esc`, the camera window's close button, or a successful scan closes only the
  camera. The controller stays available without using the camera.
- The first camera close shows a one-time notification explaining that the app
  is still in the tray.
- The tray offers **Scan with Camera**, **Scan Screen**, **Start with Windows**,
  and **Exit QR Scanner**.
- Reopening the EXE asks the existing tray instance to open the camera instead
  of creating a second controller or a second camera window.
- `Ctrl+Q` in the camera or **Exit QR Scanner** in the tray asks for
  confirmation before stopping everything.
- **Start with Windows** is off by default and starts only the controller, not
  the camera.

The controller does not currently connect to a relay or send any network
traffic. **Pair Phone** is visibly marked as a coming `v0.2` feature.

When **Scan Screen** finds different QR codes, the development build shows one
frozen in-memory preview with every detected code outlined. Moving the pointer
highlights the nearest code; only a direct click selects it. `Esc` cancels, and
the existing hostname confirmation still appears before a selected URL opens.

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
.\.venv\Scripts\python.exe launcher.py --show-fps
```

Normal performance is shown in turquoise and a value below 24 FPS is shown in
amber. Green is reserved for successful QR detection.

## Run from source

Python 3.10 or newer is required:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe launcher.py
```

Useful options:

```powershell
# Use another camera
.\.venv\Scripts\python.exe launcher.py --camera 1

# Do not open links automatically
.\.venv\Scripts\python.exe launcher.py --no-open

# Keep scanning after the first QR code
.\.venv\Scripts\python.exe launcher.py --keep-open

# Display the developer FPS overlay
.\.venv\Scripts\python.exe launcher.py --show-fps

# Scan all connected screens once
.\.venv\Scripts\python.exe launcher.py --screen
```

`QR Scanner.vbs` starts the source version without a terminal. The
`Scan Screen.vbs` launcher runs the separate one-shot screen scan without a
terminal. `start_qr_scanner.bat` keeps the terminal visible for diagnostics.

## Local Phone-to-PC developer demo

This development-only demo proves the first encrypted transport slice before a
mobile PWA or public relay is introduced:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m bridge.local_demo
```

It starts a relay bound only to `127.0.0.1`, completes a two-minute,
single-use encrypted pairing flow, derives matching phone and PC keys through
P-256 ECDH and HKDF, encrypts a sample URL with AES-256-GCM, routes the opaque
URL envelope over HTTP/WebSocket, and asks for confirmation on the PC. **No**
opens nothing; **Yes** opens the sample URL. Credentials exist only in memory.
The relay retains no URL or URL-message history; opaque pairing envelopes live
in memory only until their short session expires.

Use `--url https://example.com` to choose the test URL or `--no-dialog` for a
fully automated verification. This demo runs entirely on one computer; it is
not the mobile feature and is not exposed to the local network or internet.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe launcher.py --self-test
```

The self-test verifies OpenCV imports and QR decoding without opening a camera.

## Build the Windows executable

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\build_exe.bat
```

The build produces the terminal-free executable and a distributable ZIP:

```text
dist\Webcam-QR-Scanner-v0.2.0-dev-windows-x64.zip
```

The ZIP contains `QR-Scanner.exe`, the `Scan Screen.vbs` launcher, the project
MIT license, the third-party notice, and the complete license material for
bundled dependencies. A `SHA256SUMS.txt` file is also generated for integrity
verification.

## Project structure

- `app.py`: application flow and command-line options
- `launcher.py`: lightweight mode selection and single-controller startup
- `tray_app.py`: system-tray actions and child-process lifecycle
- `app_settings.py`: atomic per-user interface preferences
- `bridge_signals.py`: local control signals between executable modes
- `windows_startup.py`: optional current-user Windows startup entry
- `camera.py`: camera negotiation, Full HD measurement, and 720p fallback
- `qr_reader.py`: fast and thorough QR decoding
- `screen_capture.py`: one-shot, multi-monitor Windows desktop capture
- `screen_selector.py`: safe click-to-select overlay for multiple screen QR codes
- `scan_worker.py`: newest-frame-only background worker
- `scan_geometry.py`: real scan area and coordinate transformations
- `ui.py`: interface, animated scan line, and result presentation
- `links.py`: safe URL classification and browser integration
- `performance.py`: optional FPS measurement
- `protocol/`: `wqrs/1` schemas, test vectors, and independent verification tools
- `bridge/`: encrypted pairing/message codecs, PC receiver, fake phone, and local demo
- `relay/`: localhost-only FastAPI relay with in-memory opaque routing
- `tests/`: automated behavior, camera-selection, and QR-reader tests

## Security

Only explicit, valid `http://` and `https://` URLs are opened automatically.
Payloads using schemes such as `javascript:` or `file:` are never executed. A
QR code held in front of the camera does not continuously open new tabs.

Camera frames are processed locally in memory and are neither saved nor sent
outside the computer. The application does not request location information or
collect analytics, telemetry, or device identifiers. Once a valid URL is
opened, the destination website is handled by the default browser and is
subject to that browser's privacy settings.

Screen scanning is explicitly started by the user and captures the virtual
desktop only once. The captured pixels are processed locally in memory and are
not written to disk. A screen QR link is never opened without confirmation.
When different payloads are detected, the application requires the user to
click a visible QR boundary instead of choosing automatically. Pointer
proximity changes only the highlight and can never open a link.

The development system-tray controller does not activate the camera in the
background and does not connect to a relay. **Start with Windows** writes only
this application's current-user startup entry and is changed solely after the
user selects the menu option. The separate developer relay binds only to
`127.0.0.1` while its explicit demo command is running; it stores token HMAC
digests and routing IDs, but no URL or message history. Future production
Phone-to-PC networking will remain off until the user explicitly starts
pairing.

The application validates the URL scheme but cannot determine whether a website
is trustworthy or malicious. Check the hostname shown in the confirmation
dialog before opening a screen QR link.

## Roadmap

### v0.1 — Windows desktop release

- [x] Publish the source code on GitHub
- [x] Build a standalone, terminal-free Windows executable
- [x] Publish a `v0.1.0` GitHub Release
- [x] Add a screenshot, usage GIF, and release notes

### v0.1.1 — Scan QR codes displayed on the computer screen

- [x] Add a separate `Scan Screen` launcher
- [x] Capture all connected displays once without saving an image
- [x] Show the hostname and require confirmation before opening a screen URL
- [x] Block ambiguous scans containing different QR payloads
- [x] Add automated tests and a standalone Windows package

### v0.2 — Install-free PWA Phone-to-PC bridge

Planned account-free pairing with a short-lived QR code and one-time approval
on the computer. Users will open the mobile PWA over HTTPS without installing a
native app and may optionally add it to the Home Screen. The PWA will decode QR
codes on-device and offer **Open on this phone** or **Send to PC**. URLs will be
end-to-end encrypted with built-in Browser WebCrypto and delivered through an
internet relay that cannot read their contents. No local-network or location
permission will be required. The computer will validate the payload and request
confirmation before opening it by default.

Architecture, pairing protocol, threat model, and acceptance criteria are
documented in the
[v0.2 technical design (Turkish)](docs/phone-to-pc-technical-design.tr.md).

- [x] PWA-compatible `wqrs/1` JSON schemas and threat-model checklist
- [x] P-256/HKDF/AES-GCM vectors verified by Python, independent Node.js, and
  browser-compatible WebCrypto code
- [x] One-EXE desktop controller with separate camera and screen processes
- [x] System tray, one-time camera-close notice, optional Windows startup, and
  confirmed full exit
- [x] Camera stays off while only the background controller is running
- [x] Explicit click-to-select overlay for multiple screen QR codes
- [x] First encrypted end-to-end transfer through a localhost relay and fake phone
- [x] Two-minute, single-use pairing HTTP flow with encrypted approval/rejection
- [ ] Show the pairing QR and approval dialog from the tray controller
- [ ] Integrate the persistent PC receiver with the tray controller
- [ ] PWA, Browser WebCrypto, camera, and real Android/iOS browser tests

### v0.2.1 — Encrypted queue and reminders

If the computer is offline, the encrypted item may remain in the PWA's local
storage until the computer reconnects. Browsers do not guarantee background
execution, so reminders and timers will be offered only where genuinely
supported; automatic opening will remain an explicit user preference.

### v0.2.2 — Optional local-network mode

A direct local-network transport may be added later as an opt-in alternative
for users who prefer a relay-free connection while both devices are on the same
network.

## License

Copyright © 2026 [alpkonakci](https://github.com/alpkonakci).

This project is licensed under the [MIT License](LICENSE).
Bundled dependency licenses are documented in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
