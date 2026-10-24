"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { isLikelyMobileBrowser } from "../lib/device-kind";
import { parseQrPayload } from "../lib/qr-payload.mjs";
import type { QrPayloadResult } from "../lib/qr-payload.mjs";
import { getMostRecentPair } from "../lib/pair-store";
import { acknowledgeScannerReturn, parseScannerReturn } from "../lib/scanner-return";
import {
  pairingUriFromLaunchFragment,
  pairingUriFromScannedValue,
  type SenderCredentials,
} from "../lib/wqrs";
import { PairingView } from "./PairingView";
import { QrResultView } from "./QrResultView";
import { QrScannerView } from "./QrScannerView";
import { QrImageView } from "./QrImageView";
import { TextResultView } from "./TextResultView";
import { LocaleProvider, useLocale } from "../lib/i18n";
import { APP_VERSION } from "../lib/app-info";
import { PcConnectionBadge } from "./PcConnectionBadge";
import { SettingsView } from "./SettingsView";
import { HomeScreenGuide } from "./HomeScreenGuide";
import { homeScreenContext, type HomeScreenContext } from "../lib/home-screen";
import { selectHomeView, pairingGuideStatus } from "../lib/home-view";

const subscribeToStaticDeviceKind = () => () => {};
const getServerDeviceKind = () => false;

export function PwaHome() {
  return <LocaleProvider><Home /></LocaleProvider>;
}
function Home() {
  const { tr } = useLocale();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [installContext, setInstallContext] = useState<HomeScreenContext>({ platform: "other", installed: false });
  const [scannerOpen, setScannerOpen] = useState(false);
  const [imageOpen, setImageOpen] = useState(false);
  const [scanSource, setScanSource] = useState<"camera" | "image">("camera");
  const [scanResult, setScanResult] = useState<QrPayloadResult | null>(null);
  const [pairingUri, setPairingUri] = useState<string | null>(null);
  const [pairedPc, setPairedPc] = useState<SenderCredentials | null>(null);
  const [pairStoreReady, setPairStoreReady] = useState(false);
  const [pairStoreError, setPairStoreError] = useState(false);
  const [scannerReturn, setScannerReturn] = useState<ReturnType<typeof parseScannerReturn>>(null);
  const surface = useRef<HTMLElement>(null);
  const view = selectHomeView({ settingsOpen, imageOpen, pairingUri, scanResult });
  // Keep text/link results in the same focus-transition group as before.
  const resultView = view.kind === "text" || view.kind === "link";
  const currentView = scannerOpen ? "camera" : resultView ? "result" : view.kind;
  const guideStatus = pairingGuideStatus({ ready: pairStoreReady, error: pairStoreError, hasPair: pairedPc !== null });
  useEffect(() => {
    if (currentView === "camera") return;
    const frame = requestAnimationFrame(() => surface.current?.querySelector<HTMLElement>("h1")?.focus());
    return () => cancelAnimationFrame(frame);
  }, [currentView]);
  const isMobileClient = useSyncExternalStore(
    subscribeToStaticDeviceKind,
    isLikelyMobileBrowser,
    getServerDeviceKind,
  );

  useEffect(() => {
    let active = true;
    const standalone = window.matchMedia("(display-mode: standalone)");
    const readMode = () => setInstallContext(homeScreenContext({
      userAgent: navigator.userAgent, platform: navigator.platform, maxTouchPoints: navigator.maxTouchPoints,
      standalone: standalone.matches || (navigator as Navigator & { standalone?: boolean }).standalone === true,
    }));
    queueMicrotask(() => { if (active) readMode(); });
    standalone.addEventListener("change", readMode);

    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker.register("/sw.js", { scope: "/" })
        .catch(() => { /* Scanning also works without an installed service worker. */ });
    }

    getMostRecentPair()
      .then((pair) => { if (active) setPairedPc(pair); })
      .catch(() => { if (active) { setPairedPc(null); setPairStoreError(true); } })
      .finally(() => { if (active) setPairStoreReady(true); });

    const returnRequest = parseScannerReturn(window.location.hash);
    if (returnRequest) queueMicrotask(() => { if (active) setScannerReturn(returnRequest); });
    const launchPairingUri = pairingUriFromLaunchFragment(
      window.location.hash,
      window.location.origin,
    );
    if (launchPairingUri || window.location.hash.startsWith("#open=")) {
      window.history.replaceState(
        window.history.state,
        "",
        `${window.location.pathname}${window.location.search}`,
      );
      queueMicrotask(() => {
        if (active && launchPairingUri) setPairingUri(launchPairingUri);
      });
    }

    return () => {
      active = false;
      standalone.removeEventListener("change", readMode);
    };
  }, []);

  useEffect(() => {
    if (!scannerReturn) return;
    const controller = new AbortController();
    void acknowledgeScannerReturn(scannerReturn, controller.signal);
    return () => controller.abort();
  }, [scannerReturn]);

  const closeScanner = useCallback(() => setScannerOpen(false), []);
  const closeImage = useCallback(() => setImageOpen(false), []);
  const closePairing = useCallback(() => setPairingUri(null), []);

  const handleDecoded = useCallback((value: string) => {
    setScannerOpen(false);
    setImageOpen(false);
    try {
      const url = new URL(value);
      const request = url.origin === window.location.origin && url.pathname === "/"
        ? parseScannerReturn(url.hash) : null;
      if (request) {
        setPairingUri(null);
        setScanResult(null);
        setScannerReturn(request);
        return;
      }
    } catch { /* Ordinary text QR; continue with payload parsing. */ }
    const scannedPairingUri = pairingUriFromScannedValue(
      value,
      window.location.origin,
    );
    if (scannedPairingUri) {
      setPairingUri(scannedPairingUri);
      return;
    }
    setPairingUri(null);
    setScanResult(parseQrPayload(value));
  }, []);

  const startScan = (source: "camera" | "image") => {
    setScanSource(source);
    setScanResult(null);
    setPairingUri(null);
    setScannerOpen(source === "camera");
    setImageOpen(source === "image");
  };
  const startScanner = () => startScan("camera");
  const startImage = () => startScan("image");
  const scanAgain = () => startScan(scanSource);

  const startPairingScanner = () => {
    setPairingUri(null);
    setScannerOpen(true);
  };

  const clearRevokedPair = useCallback((pairId: string) => {
    setPairedPc((current) => current?.pairId === pairId ? null : current);
  }, []);

  const renderContent = () => {
    switch (view.kind) {
      case "settings":
        return <SettingsView onBack={() => setSettingsOpen(false)} />;
      case "image":
        return <QrImageView onCancel={closeImage} onDecoded={handleDecoded} />;
      case "pairing":
        return (
          <PairingView
            pairingUri={view.uri}
            existingPair={pairedPc}
            pairStoreReady={pairStoreReady}
            onPaired={setPairedPc}
            onPairInvalid={clearRevokedPair}
            onCancel={closePairing}
          />
        );
      case "text":
        return <TextResultView text={view.text} onScanAgain={scanAgain} />;
      case "link":
        return (
          <QrResultView
            result={view.result}
            pairedPc={pairedPc}
            isMobileClient={isMobileClient}
            onPairPc={startPairingScanner}
            onPairRevoked={clearRevokedPair}
            onScanAgain={scanAgain}
          />
        );
      case "home":
        return (
          <>
            <div className="hero-copy">
              <h1 id="page-title" tabIndex={-1}>{tr("Scan a QR.")}</h1>
              <p>{tr("Use your camera or choose an image. Send links to your PC.")}</p>
            </div>

            {pairedPc && (
              <PcConnectionBadge pair={pairedPc} onRevoked={clearRevokedPair}>
                <details className="connection-help">
                  <summary>{tr("How do I send another QR?")}</summary>
                  <p>{tr("Your connection is saved in this browser.")}</p>
                  <p>{tr("Bookmark this page to return later. Closing the tab does not remove your pairing.")}</p>
                  <p className="return-address">{pairedPc.relayOrigin}</p>
                  <p>{tr("Open this page in the same browser and tap Scan QR. Your phone's normal camera opens websites directly; it does not send them to your PC.")}</p>
                  <p>{tr("Lost the tab? On your PC, open Paired Phones → Open scanner on phone and scan that code. If you use another browser, private browsing or clear site data, you may need to pair again.")}</p>
                </details>
              </PcConnectionBadge>
            )}

            <section className="action-panel" aria-label={tr("Available actions")}>
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
                  <strong>{tr("Scan QR")}</strong>
                  <small id="scan-status">{tr("Scan a link, text or PC pairing code")}</small>
                </span>
                <span className="action-arrow" aria-hidden="true">→</span>
              </button>
              <button className="primary-action primary-action-ready image-action" type="button" onClick={startImage}>
                <span className="action-icon image-action-icon" aria-hidden="true">▧</span>
                <span className="action-copy"><strong>{tr("Read from image")}</strong><small>{tr("Choose a screenshot or saved QR")}</small></span>
                <span className="action-arrow" aria-hidden="true">→</span>
              </button>
            </section>

            <HomeScreenGuide context={installContext} pairing={guideStatus} tr={tr} />

            <section className="privacy-panel" aria-labelledby="privacy-title">
              <div>
                <p className="section-kicker">{tr("PRIVATE BY DEFAULT")}</p>
                <h2 id="privacy-title">{tr("Only the permissions you choose")}</h2>
              </div>
              <ul>
                <li><span aria-hidden="true">✓</span>{tr("No account")}</li>
                <li><span aria-hidden="true">✓</span>{tr("No location access")}</li>
                <li><span aria-hidden="true">✓</span>{tr("Camera only while the scanner is open")}</li>
                <li><span aria-hidden="true">✓</span>{tr("Selected images are never uploaded")}</li>
              </ul>
              <details className="camera-permission-help">
                <summary>{tr("Camera permission after refreshing?")}</summary>
                <p>
                  {tr("Your browser controls this permission. If it asks each time, you can choose Camera → Allow for this site in the browser's website settings. You do not need to allow all websites. Camera permission is separate from your saved PC pairing.")}</p>
              </details>
            </section>

            <footer>
              <span className="status-idle">
                <i aria-hidden="true" />
                {tr("On-device QR reading")}
              </span>
              <a href="/licenses/THIRD_PARTY_NOTICES.txt">{tr("Open source · Licenses")}</a>
            </footer>
          </>
        );
    }
  };

  return (
    <main className="app-shell">
      <section ref={surface} className="phone-surface" aria-labelledby={view.titleId} inert={scannerOpen}>
        <header className="brand-row">
          <div className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </div>
          <div>
            <p className="eyebrow">{tr("PHONE-TO-PC")}</p>
            <p className="brand-name">QR Scanner</p>
          </div>
          <button type="button" className="settings-toggle" onClick={() => setSettingsOpen(true)} aria-label={tr("Settings and about")}>⚙</button>
          <span className="sr-only">{APP_VERSION}</span>
        </header>
        {renderContent()}
      </section>

      {scannerOpen && (
        <QrScannerView onCancel={closeScanner} onDecoded={handleDecoded} />
      )}

    </main>
  );
}
