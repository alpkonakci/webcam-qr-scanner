"use client";
import type { HomeScreenContext } from "../lib/home-screen";

export function HomeScreenGuide({ context, pairing, tr }: {
  context: HomeScreenContext; pairing: "checking" | "available" | "missing" | "unavailable"; tr(text: string): string;
}) {
  const pairingHelp = {
    checking: "Checking the saved pairing in this window…",
    available: "The saved pairing is available in this window. It does not prove that another browser or app has it.",
    missing: "No saved PC is available in this window. To connect here, show Connect a phone on your PC and scan its pairing QR from this window.",
    unavailable: "Secure browser storage could not be read. Try a regular browser window instead of private browsing before pairing.",
  };
  return <aside className="home-screen-guide" aria-label={tr("Return easily to QR Scanner")}>
    <details>
      <summary>{tr(context.installed ? "Using the Home Screen app" : "Add QR Scanner to your Home Screen")}</summary>
      {context.installed ? <p>{tr("This window uses the pairing saved in this web app. Your regular browser may have a separate pairing.")}</p> : <>
        {context.platform !== "android" && <section aria-label="iPhone / iPad">
          <h3>iPhone / iPad · Safari</h3>
          <ol>
            <li>{tr("Open QR Scanner in Safari.")}</li>
            <li>{tr("Tap Share (or the page menu, then Share).")}</li>
            <li>{tr("Choose Add to Home Screen. Enable Open as Web App if it is offered, then tap Add.")}</li>
            <li>{tr("Open the new QR Scanner icon and check the saved PC name before sending.")}</li>
          </ol>
          <a href="https://support.apple.com/en-lamr/guide/iphone/iphea86e5236/ios" target="_blank" rel="noopener noreferrer">{tr("Apple's illustrated guide")}</a>
        </section>}
        {context.platform !== "ios" && <section aria-label="Android">
          <h3>Android · Chrome</h3>
          <ol>
            <li>{tr("Open QR Scanner in Chrome.")}</li>
            <li>{tr("Open the three-dot menu → Add to Home screen → Install, if available.")}</li>
            <li>{tr("Open the new QR Scanner icon and check the saved PC name before sending.")}</li>
          </ol>
          <a href="https://support.google.com/chrome/answer/9658361?co=GENIE.Platform%3DAndroid" target="_blank" rel="noopener noreferrer">{tr("Google's installation guide")}</a>
        </section>}
      </>}
      <p className="home-screen-warning">{tr("Pairing is stored securely in this browser. Installing a web app does not guarantee that the pairing is copied. On iPhone, the web app may use separate storage.")}</p>
      <p role={pairing === "unavailable" ? "alert" : undefined}>{tr(pairingHelp[pairing])}</p>
      <p>{tr("If the new app has no pairing, connect it once from inside that app. Your original browser pairing is not deleted. Do not share pairing keys or copy them into a URL.")}</p>
    </details>
  </aside>;
}
