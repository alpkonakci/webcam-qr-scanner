"use client";
import { useLocale } from "../lib/i18n";

import { useEffect, useRef, useState } from "react";
import type QrScanner from "qr-scanner";

interface QrScannerViewProps {
  onCancel(): void;
  onDecoded(value: string): void;
}

type CameraStatus = "starting" | "scanning" | "error";

function cameraErrorMessage(error: unknown): string {
  if (!window.isSecureContext) {
    return "Camera access requires a secure HTTPS connection.";
  }

  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Camera access was blocked. Allow camera access in your browser settings and try again.";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return "No usable camera was found on this device.";
  }
  if (name === "NotReadableError" || name === "AbortError") {
    return "The camera is already in use or could not be started.";
  }

  return "The camera could not be started. Check your browser permissions and try again.";
}

export function QrScannerView({ onCancel, onDecoded }: QrScannerViewProps) {
  const { tr } = useLocale();
  const videoRef = useRef<HTMLVideoElement>(null);
  const scannerRef = useRef<QrScanner | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const decodedRef = useRef(false);
  const [status, setStatus] = useState<CameraStatus>("starting");
  const [error, setError] = useState<string | null>(null);
  const [hasFlash, setHasFlash] = useState(false);
  const [flashOn, setFlashOn] = useState(false);

  useEffect(() => {
    let cancelled = false;
    closeButton.current?.focus();

    const closeWhenHidden = () => {
      if (document.visibilityState === "hidden") onCancel();
    };

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      onCancel();
    };

    const startScanner = async () => {
      try {
        if (!window.isSecureContext) throw new DOMException("Insecure context", "SecurityError");
        const { default: QrScannerClass } = await import("qr-scanner");
        if (cancelled || !videoRef.current) return;

        const scanner = new QrScannerClass(
          videoRef.current,
          (result) => {
            if (decodedRef.current) return;
            decodedRef.current = true;
            scanner.stop();
            onDecoded(result.data);
          },
          {
            preferredCamera: "environment",
            maxScansPerSecond: 10,
            returnDetailedScanResult: true,
            onDecodeError: () => undefined,
          },
        );

        scannerRef.current = scanner;
        await scanner.start();
        if (cancelled) {
          scanner.destroy();
          return;
        }

        setStatus("scanning");
        setHasFlash(await scanner.hasFlash().catch(() => false));
      } catch (startError) {
        if (cancelled) return;
        setStatus("error");
        setError(cameraErrorMessage(startError));
      }
    };

    document.addEventListener("visibilitychange", closeWhenHidden);
    document.addEventListener("keydown", closeOnEscape);
    window.addEventListener("pagehide", onCancel);
    void startScanner();

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", closeWhenHidden);
      document.removeEventListener("keydown", closeOnEscape);
      window.removeEventListener("pagehide", onCancel);
      scannerRef.current?.destroy();
      scannerRef.current = null;
    };
  }, [onCancel, onDecoded]);

  const toggleFlash = async () => {
    const scanner = scannerRef.current;
    if (!scanner) return;

    try {
      await scanner.toggleFlash();
      setFlashOn(scanner.isFlashOn());
    } catch {
      setHasFlash(false);
      setFlashOn(false);
    }
  };

  return (
    <section className="scanner-screen" role="dialog" aria-modal="true" aria-labelledby="scanner-title"
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
        const first = buttons[0], last = buttons.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }}>
      <video ref={videoRef} className="scanner-video" muted playsInline aria-hidden="true" />
      <div className="scanner-shade" aria-hidden="true" />

      <header className="scanner-header">
        <div>
          <p className="eyebrow">{tr("ON-DEVICE SCANNING")}</p>
          <h2 id="scanner-title">{tr("Point at a QR code")}</h2>
        </div>
        <button
          ref={closeButton}
          type="button"
          className="scanner-close"
          onClick={onCancel}
          aria-keyshortcuts="Escape"
          title={tr("Close scanner (Esc)")}
        >
          {tr("Close")}</button>
      </header>

      <div className="scanner-target" aria-hidden="true">
        <span className="corner corner-top-left" />
        <span className="corner corner-top-right" />
        <span className="corner corner-bottom-left" />
        <span className="corner corner-bottom-right" />
        {status === "scanning" && <span className="camera-scan-line" />}
      </div>

      <div className="scanner-controls" aria-live="polite">
        {status === "starting" && (
          <p className="scanner-status">{tr("Starting camera…")}</p>
        )}
        {status === "scanning" && (
          <p className="scanner-status">{tr("Keep the QR code inside the frame")}</p>
        )}
        {status === "error" && (
          <div className="camera-error" role="alert">
            <strong>{tr("Camera unavailable")}</strong>
            <p>{error && tr(error)}</p>
            <button type="button" onClick={onCancel}>{tr("Back")}</button>
          </div>
        )}
        {status === "scanning" && hasFlash && (
          <button type="button" className="flash-button" onClick={toggleFlash}>
            {flashOn ? tr("Turn flash off") : tr("Turn flash on")}
          </button>
        )}
        <p className="camera-privacy">{tr("Frames stay on this device and are never uploaded.")}</p>
      </div>
    </section>
  );
}
