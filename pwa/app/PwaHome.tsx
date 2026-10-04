"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { isLikelyMobileBrowser } from "../lib/device-kind";
import { parseWebUrl } from "../lib/url-policy.mjs";
import type { WebUrlResult } from "../lib/url-policy.mjs";
import { getMostRecentPair } from "../lib/pair-store";
import {
  pairingUriFromLaunchFragment,
  pairingUriFromScannedValue,
  type SenderCredentials,
} from "../lib/wqrs";
import { PairingView } from "./PairingView";
import { QrResultView } from "./QrResultView";
import { QrScannerView } from "./QrScannerView";

const subscribeToStaticDeviceKind = () => () => {};
const getServerDeviceKind = () => false;

export function PwaHome() {
  const [serviceWorkerReady, setServiceWorkerReady] = useState(false);
  const [scannerOpen, setScannerOpen] = useState(false);
  const [scanResult, setScanResult] = useState<WebUrlResult | null>(null);
  const [pairingUri, setPairingUri] = useState<string | null>(null);
  const [pairedPc, setPairedPc] = useState<SenderCredentials | null>(null);
  const [pairStoreReady, setPairStoreReady] = useState(false);
  const isMobileClient = useSyncExternalStore(
    subscribeToStaticDeviceKind,
    isLikelyMobileBrowser,
    getServerDeviceKind,
  );

  useEffect(() => {
    let active = true;

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .then(() => { if (active) setServiceWorkerReady(true); })
        .catch(() => { if (active) setServiceWorkerReady(false); });
    }

    getMostRecentPair()
      .then((pair) => { if (active) setPairedPc(pair); })
      .catch(() => { if (active) setPairedPc(null); })
      .finally(() => { if (active) setPairStoreReady(true); });

    const launchPairingUri = pairingUriFromLaunchFragment(
      window.location.hash,
      window.location.origin,
    );
    if (launchPairingUri) {
      window.history.replaceState(
        window.history.state,
        "",
        `${window.location.pathname}${window.location.search}`,
      );
      queueMicrotask(() => {
        if (active) setPairingUri(launchPairingUri);
      });
    }

    return () => {
      active = false;
    };
  }, []);

  const closeScanner = useCallback(() => setScannerOpen(false), []);
  const closePairing = useCallback(() => setPairingUri(null), []);

  const handleDecoded = useCallback((value: string) => {
    setScannerOpen(false);
    const scannedPairingUri = pairingUriFromScannedValue(
      value,
      window.location.origin,
    );
    if (scannedPairingUri) {
      setPairingUri(scannedPairingUri);
      return;
    }
    setPairingUri(null);
    setScanResult(parseWebUrl(value));
  }, []);

  const startScanner = () => {
    setScanResult(null);
    setPairingUri(null);
    setScannerOpen(true);
  };

  const startPairingScanner = () => {
    setPairingUri(null);
    setScannerOpen(true);
  };

  const clearRevokedPair = useCallback((pairId: string) => {
    setPairedPc((current) => current?.pairId === pairId ? null : current);
  }, []);

  return (
    <main className="app-shell">
      <section className="phone-surface" aria-labelledby="page-title">
        <header className="brand-row">
          <div className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </div>
          <div>
            <p className="eyebrow">PHONE-TO-PC</p>
            <p className="brand-name">QR Scanner</p>
          </div>
          <span className="dev-badge">v0.2 beta.4</span>
        </header>

        {pairingUri ? (
          <PairingView
            pairingUri={pairingUri}
            existingPair={pairedPc}
            pairStoreReady={pairStoreReady}
            onPaired={setPairedPc}
            onPairInvalid={clearRevokedPair}
            onCancel={closePairing}
          />
        ) : scanResult ? (
          <QrResultView
            result={scanResult}
            pairedPc={pairedPc}
            isMobileClient={isMobileClient}
            onPairPc={startPairingScanner}
            onPairRevoked={clearRevokedPair}
            onScanAgain={startScanner}
          />
        ) : (
          <>
            <div className="hero-copy">
              <div className="ready-pill">
                <span className="ready-dot" aria-hidden="true" />
                {pairedPc ? `Paired with ${pairedPc.pcLabel}` : "Camera scanner ready"}
              </div>
              <h1 id="page-title">Scan here. Continue on your PC.</h1>
              <p>
                Scan a QR web link with your phone, or scan the one-time pairing
                code shown by QR Scanner on your PC.
              </p>
            </div>

            <section className="action-panel" aria-label="Available actions">
              <button
                className="primary-action primary-action-ready"
                type="button"
                onClick={startScanner}
                aria-describedby="scan-status"
              >
                <span className="action-icon" aria-hidden="true">
                  <i />
                </span>
                <span className="action-copy">
                  <strong>Scan QR</strong>
                  <small id="scan-status">Scan a web link or PC pairing code</small>
                </span>
                <span className="action-arrow" aria-hidden="true">→</span>
              </button>

            </section>

            {pairedPc && (
              <aside className="return-panel" aria-label="Return to your scanner">
                <strong>Your connection is saved in this browser.</strong>
                <p>
                  Bookmark this page to return later. Closing the tab does not
                  remove your pairing.
                </p>
                <p className="return-address">{pairedPc.relayOrigin}</p>
                <details>
                  <summary>How do I send another QR?</summary>
                  <p>
                    Open this page in the same browser and tap Scan QR. Your
                    phone&apos;s normal camera opens websites directly; it does
                    not send them to your PC.
                  </p>
                  <p>
                    Lost the tab? On your PC, open Paired Phones → Open scanner
                    on phone and scan that code. If you use another browser,
                    private browsing or clear site data, you may need to pair again.
                  </p>
                </details>
              </aside>
            )}

            <section className="privacy-panel" aria-labelledby="privacy-title">
              <div>
                <p className="section-kicker">PRIVATE BY DEFAULT</p>
                <h2 id="privacy-title">Only the permissions you choose</h2>
              </div>
              <ul>
                <li><span aria-hidden="true">✓</span>No account</li>
                <li><span aria-hidden="true">✓</span>No location access</li>
                <li><span aria-hidden="true">✓</span>Camera only while the scanner is open</li>
              </ul>
              <details className="camera-permission-help">
                <summary>Camera permission after refreshing?</summary>
                <p>
                  Your browser controls this permission. If it asks each time,
                  you can choose Camera → Allow for this site in the browser&apos;s
                  website settings. You do not need to allow all websites.
                  Camera permission is separate from your saved PC pairing.
                </p>
              </details>
            </section>

            <footer>
              <span className={serviceWorkerReady ? "status-online" : "status-idle"}>
                <i aria-hidden="true" />
                {serviceWorkerReady ? "Scanner ready" : "Preparing scanner"}
              </span>
              <span>Open source · MIT</span>
            </footer>
          </>
        )}
      </section>

      {scannerOpen && (
        <QrScannerView onCancel={closeScanner} onDecoded={handleDecoded} />
      )}

    </main>
  );
}
