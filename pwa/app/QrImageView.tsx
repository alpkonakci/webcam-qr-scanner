"use client";
import { useLocale } from "../lib/i18n";

import { useCallback, useEffect, useRef, useState, type PointerEvent } from "react";
import { loadQrImage, scanQrImage, type LocalQrImage } from "../lib/image-qr";
import { pastedImage, readClipboardImage } from "../lib/image-clipboard.mjs";
import type { ImageCrop } from "../lib/image-policy.mjs";
import { adjustSelection } from "../lib/keyboard-crop";

interface Props { onCancel(): void; onDecoded(value: string): void }

const WHOLE_IMAGE: ImageCrop = { x: 0, y: 0, width: 1, height: 1 };

export function QrImageView({ onCancel, onDecoded }: Props) {
  const { tr } = useLocale();
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
      job.current?.abort();
      localImage.current?.dispose();
      localImage.current = null;
    };
  }, [onCancel]);

  // Both whole-image and selected-area reads have the same job lifecycle.
  // Only the latest, non-cancelled job may update the view or emit a result.
  const runRead = useCallback(async (
    operation: (signal: AbortSignal) => Promise<string | undefined>,
    fallbackMessage: string,
  ) => {
    job.current?.abort();
    const controller = new AbortController();
    job.current = controller;
    const isCurrent = () => !controller.signal.aborted && job.current === controller;
    setMessage(null);
    setBusy(true);
    try {
      const value = await operation(controller.signal);
      if (isCurrent() && value !== undefined) onDecoded(value);
    } catch (error) {
      if (isCurrent()) setMessage(error instanceof Error ? error.message : fallbackMessage);
    } finally {
      if (isCurrent()) setBusy(false);
    }
  }, [onDecoded]);

  const choose = useCallback(async (file: Blob | undefined) => {
    if (!file) return; // Dismissing the picker leaves the current image intact.
    localImage.current?.dispose();
    localImage.current = null;
    setUrl(null);
    setCrop(null);
    await runRead(async (signal) => {
      const loaded = await loadQrImage(file, signal);
      if (signal.aborted) {
        loaded.dispose();
        return;
      }
      localImage.current = loaded;
      setUrl(loaded.url);
      // Decode directly; ask for a crop only if no single QR can be chosen.
      return scanQrImage(loaded.image, WHOLE_IMAGE, signal);
    }, "This image could not be opened.");
  }, [runRead]);

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
    const image = localImage.current.image;
    await runRead((signal) => scanQrImage(image, crop, signal), "The QR code could not be read.");
  };

  return (
    <section className="image-reader" aria-labelledby="image-reader-title" aria-busy={busy}>
      <div className="image-reader-heading">
        <div><p className="eyebrow">{tr("ON-DEVICE SCANNING")}</p><h1 id="image-reader-title" tabIndex={-1}>{tr("Read from image")}</h1></div>
        <button type="button" className="scanner-close" onClick={onCancel}>{tr("Back")}</button>
      </div>
      <p className="image-help">{url && !busy
        ? tr("Drag around the QR you want to read, including its white border. Or choose another image.")
        : tr("Choose or paste an image. We'll find the QR automatically.")}</p>
      <input ref={picker} type="file" accept="image/png,image/jpeg,image/webp" className="image-file-input"
        aria-label={tr("Choose a QR image")} tabIndex={-1}
        onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; void choose(file); }} />
      <div className="image-source-actions">
      <button type="button" className="result-secondary result-secondary-enabled image-choose"
        disabled={busy} onClick={() => picker.current?.click()}>
        {url ? tr("Choose another image") : tr("Choose image")}<small>PNG · JPEG · WebP</small>
      </button>
      <button type="button" className="result-secondary result-secondary-enabled image-choose"
        disabled={busy} onClick={() => void pasteFromClipboard()}>
        {tr("Paste image")}<small>{tr("Clipboard · Ctrl+V / ⌘V")}</small>
      </button>
      </div>
      {url && !busy && (
        <>
          <div className="image-preview-frame">
            <div className="image-crop-surface" aria-label={tr("Drag to select one QR code")}
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
              <img src={url} alt={tr("Selected image for local QR scanning")} draggable={false} />
              {crop && <div className="image-crop-box" aria-hidden="true" style={{
                left: `${crop.x * 100}%`, top: `${crop.y * 100}%`,
                width: `${crop.width * 100}%`, height: `${crop.height * 100}%`,
              }} />}
            </div>
          </div>
          <div className="image-selection-actions">
            <button type="button" className="result-text-button" disabled={busy}
              onClick={() => { setCrop(WHOLE_IMAGE); setMessage(null); }}>{tr("Use whole image")}</button>
            <button type="button" className="result-text-button" disabled={busy || !crop}
              onClick={() => { setCrop(null); setMessage(null); }}>{tr("Reset selection")}</button>
          </div>
          <details className="keyboard-area-controls">
            <summary>{tr("Select an area with the keyboard")}</summary>
            <fieldset>
              <legend>{tr("Area as a percentage of the image")}</legend>
              {([ ["x", "Left (%)"], ["y", "Top (%)"], ["width", "Width (%)"], ["height", "Height (%)"] ] as const).map(([field, label]) =>
                <label key={field}>{tr(label)}
                  <input type="number" min={field === "x" || field === "y" ? 0 : 1} max={field === "x" || field === "y" ? 99 : 100} step={1}
                    value={Math.round((crop ?? WHOLE_IMAGE)[field] * 100)}
                    onChange={(event) => { setCrop(adjustSelection(crop, field, event.target.valueAsNumber)); setMessage(null); }} />
                </label>)}
            </fieldset>
          </details>
          <button type="button" className="result-primary image-read" disabled={busy || !crop || crop.width === 0 || crop.height === 0}
            onClick={() => void read()}>{busy ? tr("Reading…") : tr("Read selected area")}</button>
        </>
      )}
      {busy && <p role="status" className="image-help">{url ? tr("Searching for a QR…") : tr("Preparing image…")}</p>}
      {message && <p role="alert" className="delivery-status delivery-status-error image-feedback">{tr(message)}</p>}
      <p className="image-privacy">{tr("Images stay on this device. No upload or camera permission. Clipboard access only when you paste. Up to 10 MB.")}</p>
    </section>
  );
}
