"use client";
import { useLocale } from "../lib/i18n";

import { useRef, useState } from "react";

export function TextResultView({ text, onScanAgain }: { text: string; onScanAgain(): void }) {
  const { tr } = useLocale();
  const [message, setMessage] = useState("Nothing was opened or sent to your PC.");
  const field = useRef<HTMLTextAreaElement>(null);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setMessage("Text copied.");
    } catch {
      field.current?.focus();
      field.current?.select();
      setMessage("Press and hold the selected text, then choose Copy.");
    }
  };

  return (
    <section className="result-section" aria-live="polite">
      <div className="result-pill result-pill-success">{tr("Text QR decoded")}</div>
      <h1 id="text-result-title" tabIndex={-1}>{tr("Text ready.")}</h1>
      <div className="result-card">
        <label className="result-label" htmlFor="qr-text">{tr("QR CONTENT")}</label>
        <textarea id="qr-text" className="qr-text-content" ref={field} value={text} readOnly rows={7} />
        <p className="result-note">Text only. Copy only content you trust.</p>
      </div>
      <div className="result-actions">
        <button type="button" className="result-primary" onClick={() => { void copy(); }}>{tr("Copy text")}</button>
        <p className="result-note" role="status">{tr(message)}</p>
        <button type="button" className="result-text-button" onClick={onScanAgain}>{tr("Scan another QR")}</button>
      </div>
    </section>
  );
}
