"use client";

import { useCallback, useEffect, useRef, useState, type PointerEvent } from "react";
import { loadQrImage, scanQrImage, type LocalQrImage } from "../lib/image-qr";
import { pastedImage, readClipboardImage } from "../lib/image-clipboard.mjs";
import type { ImageCrop } from "../lib/image-policy.mjs";

interface Props { onCancel(): void; onDecoded(value: string): void }

export function QrImageView({ onCancel, onDecoded }: Props) {
  const picker = useRef<HTMLInputElement>(null);
  const localImage = useRef<LocalQrImage | null>(null);
  const job = useRef<AbortController | null>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [crop, setCrop] = useState<ImageCrop | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onCancel(); }
    };
    document.addEventListener("keydown", escape);
    window.addEventListener("pagehide", onCancel);
    return () => {
      document.removeEventListener("keydown", escape);
      window.removeEventListener("pagehide", onCancel);
      job.current?.abort(); localImage.current?.dispose(); localImage.current = null;
    };
  }, [onCancel]);

  const choose = useCallback(async (file: Blob | undefined) => {
    if (!file) return; // Dismissing the picker leaves the current image intact.
    job.current?.abort(); localImage.current?.dispose(); localImage.current = null;
    const controller = new AbortController(); job.current = controller;
    setUrl(null); setCrop(null); setMessage(null); setBusy(true);
    try {
      const loaded = await loadQrImage(file, controller.signal);
      if (controller.signal.aborted || job.current !== controller) { loaded.dispose(); return; }
      localImage.current = loaded; setUrl(loaded.url);
      // A selected/pasted image is already the user's intended scan input.
      // Ask for a crop only when whole-image decoding cannot choose one QR.
      const value = await scanQrImage(loaded.image, { x: 0, y: 0, width: 1, height: 1 }, controller.signal);
      if (!controller.signal.aborted && job.current === controller) onDecoded(value);
    } catch (error) {
      if (!controller.signal.aborted && job.current === controller) {
        setMessage(error instanceof Error ? error.message : "This image could not be opened.");
      }
    } finally {
      if (!controller.signal.aborted && job.current === controller) setBusy(false);
    }
  }, [onDecoded]);

  useEffect(() => {
    const paste = (event: ClipboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.closest("input, textarea, [contenteditable]")) return;
      event.preventDefault();
      if (busy) return;
      try { void choose(pastedImage(event.clipboardData)); }
      catch (error) { setMessage(error instanceof Error ? error.message : "Paste one QR image."); }
    };
    document.addEventListener("paste", paste);
    return () => document.removeEventListener("paste", paste);
  }, [busy, choose]);

  const pasteFromClipboard = async () => {
    if (busy) return;
    job.current?.abort();
    const controller = new AbortController(); job.current = controller;
    setBusy(true); setMessage(null);
    try {
      const image = await readClipboardImage(navigator.clipboard, controller.signal);
      if (!controller.signal.aborted && job.current === controller) await choose(image);
    } catch (error) {
      if (!controller.signal.aborted && job.current === controller) {
        setMessage(error instanceof DOMException && error.name === "NotAllowedError"
          ? "Clipboard access was not allowed. Try Ctrl+V / ⌘V, or choose an image."
          : error instanceof Error ? error.message : "Could not paste. Choose an image instead.");
      }
    } finally {
      if (!controller.signal.aborted && job.current === controller) setBusy(false);
    }
  };

  const position = (event: PointerEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return { x: Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
      y: Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)) };
  };
  const updateCrop = (event: PointerEvent<HTMLDivElement>) => {
    if (!start.current || busy) return;
    const point = position(event);
    setCrop({ x: Math.min(start.current.x, point.x), y: Math.min(start.current.y, point.y),
      width: Math.abs(point.x - start.current.x), height: Math.abs(point.y - start.current.y) });
  };
  const read = async () => {
    if (busy || !crop || !localImage.current) return;
    job.current?.abort();
    const controller = new AbortController(); job.current = controller;
    setBusy(true); setMessage(null);
    try {
      const value = await scanQrImage(localImage.current.image, crop, controller.signal);
      if (!controller.signal.aborted && job.current === controller) onDecoded(value);
    } catch (error) {
      if (!controller.signal.aborted && job.current === controller) {
        setMessage(error instanceof Error ? error.message : "The QR code could not be read.");
      }
    } finally {
      if (!controller.signal.aborted && job.current === controller) setBusy(false);
    }
  };

  return (
    <section className="image-reader" aria-labelledby="image-reader-title" aria-busy={busy}>
      <div className="image-reader-heading">
        <div><p className="eyebrow">ON-DEVICE SCANNING</p><h1 id="image-reader-title">Read from image</h1></div>
        <button type="button" className="scanner-close" onClick={onCancel}>Back</button>
      </div>
      <p className="image-help">{url && !busy
        ? "Drag around the QR you want to read, including its white border. Or choose another image."
        : "Choose or paste an image. We'll find the QR automatically."}</p>
      <input ref={picker} type="file" accept="image/png,image/jpeg,image/webp" className="image-file-input"
        aria-label="Choose a QR image" tabIndex={-1}
        onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; void choose(file); }} />
      <div className="image-source-actions">
      <button type="button" className="result-secondary result-secondary-enabled image-choose"
        disabled={busy} onClick={() => picker.current?.click()}>
        {url ? "Choose another image" : "Choose image"}<small>PNG · JPEG · WebP</small>
      </button>
      <button type="button" className="result-secondary result-secondary-enabled image-choose"
        disabled={busy} onClick={() => void pasteFromClipboard()}>
        Paste image<small>Clipboard · Ctrl+V / ⌘V</small>
      </button>
      </div>
      {url && !busy && (
        <>
          <div className="image-preview-frame">
            <div className="image-crop-surface" aria-label="Drag to select one QR code"
              onPointerDown={(event) => {
                if (busy || (event.pointerType === "mouse" && event.button !== 0)) return;
                event.currentTarget.setPointerCapture(event.pointerId);
                start.current = position(event); setCrop(null); setMessage(null);
              }}
              onPointerMove={updateCrop}
              onPointerUp={(event) => { updateCrop(event); start.current = null; }}
              onPointerCancel={() => { start.current = null; setCrop(null); }}>
              {/* Local, validated blob: deliberately not sent to an image optimizer. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={url} alt="Selected image for local QR scanning" draggable={false} />
              {crop && <div className="image-crop-box" aria-hidden="true" style={{
                left: `${crop.x * 100}%`, top: `${crop.y * 100}%`,
                width: `${crop.width * 100}%`, height: `${crop.height * 100}%`,
              }} />}
            </div>
          </div>
          <div className="image-selection-actions">
            <button type="button" className="result-text-button" disabled={busy}
              onClick={() => { setCrop({ x: 0, y: 0, width: 1, height: 1 }); setMessage(null); }}>Use whole image</button>
            <button type="button" className="result-text-button" disabled={busy || !crop}
              onClick={() => { setCrop(null); setMessage(null); }}>Reset selection</button>
          </div>
          <button type="button" className="result-primary image-read" disabled={busy || !crop || crop.width === 0 || crop.height === 0}
            onClick={() => void read()}>{busy ? "Reading…" : "Read selected area"}</button>
        </>
      )}
      {busy && <p role="status" className="image-help">{url ? "Searching for a QR…" : "Preparing image…"}</p>}
      {message && <p role="alert" className="delivery-status delivery-status-error image-feedback">{message}</p>}
      <p className="image-privacy">Images stay on this device. No upload or camera permission. Clipboard access only when you paste. Up to 10 MB.</p>
    </section>
  );
}
