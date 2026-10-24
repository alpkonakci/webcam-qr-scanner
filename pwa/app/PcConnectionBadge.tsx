"use client";
import { useEffect, useState, type ReactNode } from "react";
import { getPcConnection, type PcConnection } from "../lib/relay-client";
import { freshConnection } from "../lib/connection-state";
import type { SenderCredentials } from "../lib/wqrs";
import { useLocale } from "../lib/i18n";
export function PcConnectionBadge({ pair, onRevoked, children }: { pair: SenderCredentials; onRevoked(pairId: string): void; children?: ReactNode }) {
  const { tr, language } = useLocale();
  const [value, setValue] = useState<PcConnection | null>(null);
  const [lastCheck, setLastCheck] = useState<number | null>(null);
  const [now, setNow] = useState(0);
  const [request, setRequest] = useState(0);
  const [busy, setBusy] = useState(false);
  const [freshUntil, setFreshUntil] = useState(0);
  useEffect(() => {
    let active = true;
    let inFlight = false;
    let current: AbortController | null = null;
    const check = async () => {
      if (!active || inFlight || document.visibilityState === "hidden") return;
      inFlight = true;
      current = new AbortController();
      const controller = current;
      const started = performance.now();
      const timeout = setTimeout(() => controller.abort(), 8000);
      setBusy(true);
      try {
        const status = await getPcConnection(pair, { signal: controller.signal });
        if (!active || controller.signal.aborted) return;
        if (status.pairStatus === "revoked") { onRevoked(pair.pairId); return; }
        // Subtract the entire round trip; network delay cannot extend a lease.
        setFreshUntil(started + status.validForSeconds * 1000);
        setValue(status); setLastCheck(Date.now()); setNow(performance.now());
      } catch { if (active) setValue(null); }
      finally { clearTimeout(timeout); inFlight = false; if (active) setBusy(false); }
    };
    queueMicrotask(() => void check());
    const refresh = setInterval(() => void check(), 15_000);
    const tick = setInterval(() => setNow(performance.now()), 1000);
    const visibility = () => {
      if (document.visibilityState === "hidden") { current?.abort(); setValue(null); }
      else { setValue(null); void check(); }
    };
    document.addEventListener("visibilitychange", visibility);
    return () => { active = false; current?.abort(); clearInterval(refresh); clearInterval(tick); document.removeEventListener("visibilitychange", visibility); };
  }, [pair, onRevoked, request]);
  const status = freshConnection(value, freshUntil, now);
  return <section className={`pc-connection pc-connection-${status}`} aria-label={tr("Pairing saved")}>
    <div className="pc-connection-label"><span>{tr("Pairing saved")}: {pair.pcLabel}</span></div>
    <p role="status">{tr(status === "reachable" ? "PC reachable" : status === "unreachable" ? "PC not reachable at last check" : "Connection not confirmed")}</p>
    {lastCheck && <small>{tr("Last check")}: {new Date(lastCheck).toLocaleTimeString(language === "tr" ? "tr-TR" : "en-GB")}</small>}
    <button type="button" disabled={busy} onClick={() => setRequest((n) => n + 1)}>{tr(busy ? "Checking connection…" : "Check connection")}</button>
    <small>{tr("A saved pairing does not mean the PC is online.")}</small>
    {children}
  </section>;
}
