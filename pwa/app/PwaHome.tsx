"use client";

import { useCallback, useEffect, useState } from "react";
import { parseWebUrl } from "../lib/url-policy.mjs";
import type { WebUrlResult } from "../lib/url-policy.mjs";
import { getMostRecentPair } from "../lib/pair-store";
import {
  isPairingUri,
  pairingUriFromLaunchFragment,
  type SenderCredentials,
} from "../lib/wqrs";
import { PairingView } from "./PairingView";
import { QrResultView } from "./QrResultView";
import { QrScannerView } from "./QrScannerView";

interface InstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  const iosNavigator = navigator as Navigator & { standalone?: boolean };
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    iosNavigator.standalone === true
  );
}

export function PwaHome() {
  const [installPrompt, setInstallPrompt] =
    useState<InstallPromptEvent | null>(null);
  const [showInstallHelp, setShowInstallHelp] = useState(false);
  const [installed, setInstalled] = useState(isStandalone);
  const [serviceWorkerReady, setServiceWorkerReady] = useState(false);
  const [scannerOpen, setScannerOpen] = useState(false);
  const [scanResult, setScanResult] = useState<WebUrlResult | null>(null);
  const [pairingUri, setPairingUri] = useState<string | null>(null);
  const [pairedPc, setPairedPc] = useState<SenderCredentials | null>(null);
  const [pairStoreReady, setPairStoreReady] = useState(false);

  useEffect(() => {
    let active = true;
    const handleInstallPrompt = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as InstallPromptEvent);
    };

    const handleInstalled = () => {
      setInstalled(true);
      setInstallPrompt(null);
      setShowInstallHelp(false);
    };

    window.addEventListener("beforeinstallprompt", handleInstallPrompt);
    window.addEventListener("appinstalled", handleInstalled);

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .then(() => setServiceWorkerReady(true))
        .catch(() => setServiceWorkerReady(false));
    }

    getMostRecentPair()
      .then(setPairedPc)
      .catch(() => setPairedPc(null))
      .finally(() => setPairStoreReady(true));

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
      window.removeEventListener("beforeinstallprompt", handleInstallPrompt);
      window.removeEventListener("appinstalled", handleInstalled);
    };
  }, []);

  const closeScanner = useCallback(() => setScannerOpen(false), []);

  const handleDecoded = useCallback((value: string) => {
    setScannerOpen(false);
    if (isPairingUri(value)) {
      setScanResult(null);
      setPairingUri(value);
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

  const requestInstall = async () => {
    if (installed) return;

    if (!installPrompt) {
      setShowInstallHelp(true);
      return;
    }

    await installPrompt.prompt();
    const choice = await installPrompt.userChoice;
    setInstallPrompt(null);
    if (choice.outcome === "accepted") setInstalled(true);
  };

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
          <span className="dev-badge">v0.2 preview</span>
        </header>

        {pairingUri ? (
          <PairingView
            pairingUri={pairingUri}
            existingPair={pairedPc}
            pairStoreReady={pairStoreReady}
            onPaired={setPairedPc}
            onCancel={() => setPairingUri(null)}
          />
        ) : scanResult ? (
          <QrResultView result={scanResult} pairedPc={pairedPc} onScanAgain={startScanner} />
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

              <button
                className="secondary-action"
                type="button"
                onClick={requestInstall}
                disabled={installed}
              >
                <span>{installed ? "Added to Home Screen" : "Install app"}</span>
                <span aria-hidden="true">{installed ? "✓" : "↓"}</span>
              </button>
            </section>

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

      {showInstallHelp && (
        <div className="sheet-backdrop" role="presentation">
          <section
            className="install-sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="install-title"
          >
            <div className="sheet-handle" aria-hidden="true" />
            <p className="section-kicker">INSTALL OPTIONAL</p>
            <h2 id="install-title">Add QR Scanner to your Home Screen</h2>
            <p>
              On iPhone, open the Share menu and choose <strong>Add to Home
              Screen</strong>. On Android, open the browser menu and choose
              <strong> Install app</strong> or <strong>Add to Home screen</strong>.
            </p>
            <button type="button" onClick={() => setShowInstallHelp(false)}>
              Got it
            </button>
          </section>
        </div>
      )}
    </main>
  );
}
