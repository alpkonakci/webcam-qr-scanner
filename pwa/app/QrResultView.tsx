"use client";

import { useState } from "react";
import { sendUrlToPc } from "../lib/relay-client";
import type { SenderCredentials } from "../lib/wqrs";
import type { WebUrlResult } from "../lib/url-policy.mjs";

interface QrResultViewProps {
  result: WebUrlResult;
  pairedPc: SenderCredentials | null;
  isMobileClient: boolean;
  onPairPc(): void;
  onScanAgain(): void;
}

type DeliveryState = "idle" | "sending" | "delivered" | "error";

export function QrResultView({
  result,
  pairedPc,
  isMobileClient,
  onPairPc,
  onScanAgain,
}: QrResultViewProps) {
  const [deliveryState, setDeliveryState] = useState<DeliveryState>("idle");
  const [deliveryMessage, setDeliveryMessage] = useState("");
  if (!result.ok) {
    return (
      <section className="result-section" aria-live="polite">
        <div className="result-pill result-pill-warning">QR rejected</div>
        <h1>That code is not a safe web link.</h1>
        <div className="result-card result-card-warning" role="alert">
          <p>{result.reason}</p>
          <p className="result-note">Nothing was opened or sent.</p>
        </div>
        <button type="button" className="result-primary" onClick={onScanAgain}>
          Scan another QR
        </button>
      </section>
    );
  }

  const openInNewTab = () => {
    window.open(result.href, "_blank", "noopener,noreferrer");
  };

  const sendToPc = async () => {
    if (!pairedPc || deliveryState === "sending") return;
    setDeliveryState("sending");
    setDeliveryMessage(`Sending securely to ${pairedPc.pcLabel}...`);
    try {
      await sendUrlToPc(pairedPc, result.href);
      setDeliveryState("delivered");
      setDeliveryMessage(`${pairedPc.pcLabel} received and verified the link.`);
    } catch (error) {
      setDeliveryState("error");
      setDeliveryMessage(error instanceof Error ? error.message : "The link was not delivered.");
    }
  };

  return (
    <section className="result-section" aria-live="polite">
      <div className="result-pill result-pill-success">QR decoded</div>
      <h1>Link ready.</h1>

      <div className="result-card">
        <p className="result-label">WEBSITE</p>
        <p className="result-hostname">{result.hostname}</p>
        <p className="result-label result-address-label">FULL ADDRESS</p>
        <p className="result-address">{result.href}</p>
        {result.insecure && (
          <p className="http-warning">This address uses HTTP and is not encrypted.</p>
        )}
      </div>

      <div className="result-actions">
        <button
          type="button"
          className="result-primary"
          onClick={openInNewTab}
        >
          Open link in new tab
        </button>
        {isMobileClient &&
          (pairedPc ? (
            <button
              type="button"
              className="result-secondary result-secondary-enabled"
              disabled={deliveryState === "sending" || deliveryState === "delivered"}
              onClick={sendToPc}
            >
              <span>{deliveryState === "sending" ? "Sending..." : "Send to PC"}</span>
              <small>{pairedPc.pcLabel}</small>
            </button>
          ) : (
            <button
              type="button"
              className="result-secondary result-secondary-enabled"
              onClick={onPairPc}
            >
              <span>Pair a PC</span>
              <small>Scan the pairing QR shown on your PC</small>
            </button>
          ))}
        {deliveryMessage && (
          <p
            className={`delivery-status delivery-status-${deliveryState}`}
            role={deliveryState === "error" ? "alert" : "status"}
          >
            {deliveryMessage}
          </p>
        )}
        <button type="button" className="result-text-button" onClick={onScanAgain}>
          Scan another QR
        </button>
      </div>
    </section>
  );
}
