"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { defaultPhoneLabel, removePair } from "../lib/pair-store";
import {
  cancelPairingFromPhone,
  checkStoredPair,
  notifyPairingOpened,
  pairWithPc,
} from "../lib/relay-client";
import { parsePairingUri, type SenderCredentials } from "../lib/wqrs";

interface PairingViewProps {
  pairingUri: string;
  existingPair: SenderCredentials | null;
  pairStoreReady: boolean;
  onPaired(credentials: SenderCredentials): void;
  onPairInvalid(pairId: string): void;
  onCancel(): void;
}

type PairingState = "ready" | "check_error" | "waiting" | "error";

export function PairingView({
  pairingUri,
  existingPair,
  pairStoreReady,
  onPaired,
  onPairInvalid,
  onCancel,
}: PairingViewProps) {
  const [phoneLabel] = useState(defaultPhoneLabel);
  const [state, setState] = useState<PairingState>("ready");
  const [message, setMessage] = useState("");
  const [replaceExisting, setReplaceExisting] = useState(false);
  const [checkAttempt, setCheckAttempt] = useState(0);
  const automaticPairingStarted = useRef(false);
  const preview = useMemo(() => {
    try {
      const qr = parsePairingUri(pairingUri);
      return {
        ok: true as const,
        hostname: new URL(qr.relayOrigin).hostname,
        relayOrigin: qr.relayOrigin,
        deviceId: qr.deviceId,
      };
    } catch (error) {
      return {
        ok: false as const,
        reason: error instanceof Error ? error.message : "Pairing code is invalid.",
      };
    }
  }, [pairingUri]);

  useEffect(() => {
    if (!preview.ok) return;
    const controller = new AbortController();
    void notifyPairingOpened(pairingUri, controller.signal).catch(() => undefined);
    return () => controller.abort();
  }, [pairingUri, preview.ok]);

  const cancelUnusedPairing = useCallback(() => {
    onCancel();
    void cancelPairingFromPhone(pairingUri).catch(() => undefined);
  }, [onCancel, pairingUri]);

  const beginPairing = useCallback(async () => {
    if (!preview.ok || state === "waiting" || !pairStoreReady) return;
    setState("waiting");
    setMessage("Connecting securely to your PC…");
    try {
      const credentials = await pairWithPc(pairingUri, phoneLabel.trim());
      onPaired(credentials);
      onCancel();
      if (existingPair && existingPair.pairId !== credentials.pairId) {
        void removePair(existingPair.pairId).catch(() => undefined);
      }
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : "Pairing stopped safely.");
    }
  }, [existingPair, onCancel, onPaired, pairStoreReady, pairingUri, phoneLabel, preview.ok, state]);

  const samePcAlreadyPaired = Boolean(
    preview.ok &&
    existingPair?.deviceId === preview.deviceId &&
    existingPair.relayOrigin === preview.relayOrigin,
  );

  useEffect(() => {
    if (!preview.ok || !pairStoreReady || !samePcAlreadyPaired || !existingPair) return;
    let cancelled = false;
    const controller = new AbortController();
    void checkStoredPair(existingPair, { signal: controller.signal }).then((status) => {
      if (cancelled) return;
      if (status === "active") {
        cancelUnusedPairing();
        return;
      }
      onPairInvalid(existingPair.pairId);
      setState("ready");
    }).catch((error) => {
      if (cancelled) return;
      setMessage(error instanceof Error ? error.message : "The saved connection could not be checked.");
      setState("check_error");
    });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [cancelUnusedPairing, checkAttempt, existingPair, onPairInvalid, pairStoreReady, preview.ok, samePcAlreadyPaired]);

  useEffect(() => {
    if (
      !preview.ok || !pairStoreReady || samePcAlreadyPaired ||
      automaticPairingStarted.current || state !== "ready"
    ) return;
    if (existingPair && !replaceExisting) return;
    automaticPairingStarted.current = true;
    queueMicrotask(() => void beginPairing());
  }, [
    beginPairing,
    existingPair,
    pairStoreReady,
    preview.ok,
    replaceExisting,
    samePcAlreadyPaired,
    state,
  ]);

  if (!preview.ok) {
    return (
      <section className="result-section" aria-live="polite">
        <div className="result-pill result-pill-warning">Pairing rejected</div>
        <h1>This pairing code is not valid.</h1>
        <div className="result-card result-card-warning" role="alert">
          <p>{preview.reason}</p>
          <p className="result-note">No credential was created or stored.</p>
        </div>
        <button type="button" className="result-primary" onClick={onCancel}>Scan again</button>
      </section>
    );
  }

  if (!pairStoreReady) {
    return (
      <section className="result-section pairing-section" aria-live="polite">
        <div className="result-pill pairing-pill">Checking pairing</div>
        <h1>Preparing secure storage.</h1>
        <p className="pairing-status">Checking this browser for an existing PC pairing…</p>
      </section>
    );
  }

  if (samePcAlreadyPaired && state !== "waiting") {
    return (
      <section className="result-section pairing-section" aria-live="polite">
        <div className="result-pill result-pill-success">Saved connection</div>
        <h1>{state === "check_error" ? "Connection check stopped." : "Checking your PC connection."}</h1>
        <p className="pairing-status" role={state === "check_error" ? "alert" : "status"}>
          {state === "check_error" ? message : "Checking whether this phone still has access…"}
        </p>
        {state === "check_error" && (
          <div className="result-actions">
            <button type="button" className="result-primary" onClick={() => {
              setState("ready");
              setCheckAttempt((attempt) => attempt + 1);
            }}>Try again</button>
            <button type="button" className="result-text-button" onClick={cancelUnusedPairing}>Cancel</button>
          </div>
        )}
        {state === "ready" && (
          <button type="button" className="result-text-button" onClick={cancelUnusedPairing}>Cancel</button>
        )}
      </section>
    );
  }

  if (existingPair && !replaceExisting) {
    return (
      <section className="result-section pairing-section" aria-live="polite">
        <div className="result-pill result-pill-success">Already paired</div>
        <h1>This browser is already connected.</h1>
        <div className="result-card pairing-card">
          <p className="result-label">PAIRED PC</p>
          <p className="result-hostname">{existingPair.pcLabel}</p>
          <p className="result-note">
            Continue using the existing secure pairing. Replace it only if the
            old connection no longer works or you intend to connect this
            browser to another PC.
          </p>
        </div>
        <div className="result-actions">
          <button type="button" className="result-primary" onClick={cancelUnusedPairing}>
            Continue with {existingPair.pcLabel}
          </button>
          <button
            type="button"
            className="result-text-button"
            onClick={() => setReplaceExisting(true)}
          >
            Replace pairing
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="result-section pairing-section" aria-live="polite">
      <div className="result-pill pairing-pill">PC pairing code</div>
      <h1>
        {state === "error"
            ? "Pairing stopped."
            : "Connecting your phone."}
      </h1>

      <div className="result-card pairing-card">
        <p className="result-label">SECURE CONNECTION</p>
        <p className="result-hostname">{preview.hostname}</p>
        <p className="result-note">
          {phoneLabel} will use this encrypted connection. Your PC still asks
          before opening every link.
        </p>
        {replaceExisting && existingPair && (
          <p className="pairing-status pairing-status-error">
            Replacing {existingPair.pcLabel} creates a new secure pairing.
          </p>
        )}
      </div>

      {message && (
        <p className={`pairing-status pairing-status-${state}`} role={state === "error" ? "alert" : "status"}>
          {message}
        </p>
      )}

      <div className="result-actions">
        {state === "error" ? (
          <button
            type="button"
            className="result-primary"
            onClick={() => {
              automaticPairingStarted.current = true;
              void beginPairing();
            }}
          >
            Try again
          </button>
        ) : null}
        <button type="button" className="result-text-button" disabled={state === "waiting"} onClick={cancelUnusedPairing}>
          Cancel
        </button>
      </div>
    </section>
  );
}
