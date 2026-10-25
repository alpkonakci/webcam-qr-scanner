import { NextResponse, type NextRequest } from "next/server.js";
import { buildContentSecurityPolicy } from "./lib/content-security-policy.ts";

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.getRandomValues(new Uint8Array(16))).toString("base64");
  const csp = buildContentSecurityPolicy(process.env.NODE_ENV === "development", nonce);
  const requestHeaders = new Headers(request.headers);
  // Never trust an incoming nonce or policy. Next reads this policy while rendering.
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  response.headers.set("Cache-Control", "private, no-store");
  return response;
}

export const config = {
  matcher: ["/((?!v1(?:/|$)|healthz$|readyz$|_next/|icons/|licenses/|manifest.webmanifest$|sw.js$|og.png$|favicon.ico$).*)"],
};
