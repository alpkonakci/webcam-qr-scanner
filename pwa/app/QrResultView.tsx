"use client";

import { useEffect, useRef, useState } from "react";
import {
  checkUrlDelivery,
  isPairRevokedError,
  PendingDeliveryError,
  RelayClientError,
  removePairIfRevoked,
  sendUrlToPc,
  watchUrlDelivery,
} from "../lib/relay-client";
import type { SenderCredentials } from "../lib/wqrs";
import type { WebUrlResult } from "../lib/url-policy.mjs";

interface QrResultViewProps {
  result: WebUrlResult;
  pairedPc: SenderCredentials | null;
  isMobileClient: boolean;
  onPairPc(): void;
  onPairRevoked(pairId: string): void;
  onScanAgain(): void;
}

type DeliveryState = "idle" | "sending" | "checking" | "pending" | "unconfirmed" | "delivered" | "error";

export function QrResultView({
  result,
  pairedPc,
  isMobileClient,
  onPairPc,
  onPairRevoked,
  onScanAgain,
}: QrResultViewProps) {
  const [deliveryState, setDeliveryState] = useState<DeliveryState>("idle");
  const [deliveryMessage, setDeliveryMessage] = useState("");
  const deliveryBusy = useRef(false);
  const activeRequest = useRef<AbortController | null>(null);
  useEffect(() => () => activeRequest.current?.abort(), []);
  const awaitingReceipt = deliveryState === "pending" || deliveryState === "checking";
  useEffect(() => {
    if (!awaitingReceipt || !pairedPc || !result.ok) return;
    const controller = new AbortController();
    void watchUrlDelivery(pairedPc, result.href, controller.signal).then(() => {
      if (controller.signal.aborted) return;
      setDeliveryState("delivered");
      setDeliveryMessage(`${pairedPc.pcLabel} received and verified the link.`);
    }).catch(async (error: unknown) => {
      if (controller.signal.aborted) return;
      if (isPairRevokedError(error)) {
        try { await removePairIfRevoked(error, pairedPc.pairId); } catch { /* Clear this session below. */ }
        if (controller.signal.aborted) return;
        onPairRevoked(pairedPc.pairId);
      }
      setDeliveryState(error instanceof RelayClientError && error.code === "delivery_receipt_expired" ? "unconfirmed" : "error");
      setDeliveryMessage(error instanceof Error ? error.message : "Delivery could not be verified. Check your PC.");
    });
    return () => controller.abort();
  }, [awaitingReceipt, onPairRevoked, pairedPc, result]);
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

  const sendToPc = async (checkOnly = false) => {
    if (!pairedPc || deliveryBusy.current || deliveryState === "delivered" || deliveryState === "unconfirmed") return;
    deliveryBusy.current = true;
    const controller = new AbortController();
    activeRequest.current = controller;
    setDeliveryState(checkOnly ? "checking" : "sending");
    setDeliveryMessage(checkOnly ? "Checking the existing delivery..." : `Sending securely to ${pairedPc.pcLabel}...`);
    try {
      if (checkOnly) await checkUrlDelivery(pairedPc, result.href, controller.signal);
      else await sendUrlToPc(pairedPc, result.href, controller.signal);
      if (controller.signal.aborted) return;
      setDeliveryState("delivered");
      setDeliveryMessage(`${pairedPc.pcLabel} received and verified the link.`);
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof PendingDeliveryError) {
        setDeliveryState("pending");
        setDeliveryMessage(error.message);
        return;
      }
      if (error instanceof RelayClientError && error.code === "delivery_receipt_expired") {
        setDeliveryState("unconfirmed");
        setDeliveryMessage(error.message);
        return;
      }
      if (isPairRevokedError(error)) {
        try {
          await removePairIfRevoked(error, pairedPc.pairId);
        } catch {
          // The invalid credentials are still cleared from this session below.
          // A later successful pairing replaces any stale browser record.
        }
        onPairRevoked(pairedPc.pairId);
        setDeliveryState("error");
        setDeliveryMessage(
          "Access to this PC was removed. Pair a PC again to keep using Send to PC.",
        );
        return;
      }
      setDeliveryState("error");
      setDeliveryMessage(error instanceof Error ? error.message : "The link was not delivered.");
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
      deliveryBusy.current = false;
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
              disabled={deliveryState === "sending" || deliveryState === "checking" || deliveryState === "pending" || deliveryState === "unconfirmed" || deliveryState === "delivered"}
              onClick={() => { void sendToPc(); }}
            >
              <span>{deliveryState === "sending" ? "Sending..." : deliveryState === "delivered" ? "Received by PC" : deliveryState === "unconfirmed" ? "Check your PC" : deliveryState === "pending" || deliveryState === "checking" ? "Awaiting receipt" : "Send to PC"}</span>
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
            {awaitingReceipt && <span className="result-note"> Status is checked automatically while this page is open.</span>}
          </p>
        )}
        {pairedPc && (deliveryState === "pending" || deliveryState === "checking") && (
          <button
            type="button"
            className="result-secondary result-secondary-enabled"
            disabled={deliveryState === "checking"}
            onClick={() => { void sendToPc(true); }}
          >
            <span>{deliveryState === "checking" ? "Checking..." : "Check delivery status"}</span>
            <small>No new link will be sent</small>
          </button>
        )}
        <button type="button" className="result-text-button" onClick={onScanAgain}>
          Scan another QR
        </button>
      </div>
    </section>
  );
}
