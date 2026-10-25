/** Nonces authorize framework scripts, never arbitrary inline JavaScript. */
export function buildContentSecurityPolicy(isDevelopment: boolean, nonce?: string): string {
  if (nonce !== undefined && !/^[A-Za-z0-9+/]{22,}={0,2}$/.test(nonce)) {
    throw new Error("Invalid CSP nonce");
  }
  const scriptSources = ["'self'"];
  if (nonce) scriptSources.push(`'nonce-${nonce}'`);
  if (isDevelopment) scriptSources.push("'unsafe-eval'");
  return [
    "default-src 'self'",
    "base-uri 'none'",
    "connect-src 'self'",
    "font-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "img-src 'self' data: blob:",
    "manifest-src 'self'",
    "object-src 'none'",
    `script-src ${scriptSources.join(" ")}`,
    // Image crop geometry uses React style attributes. This does not allow scripts.
    "style-src 'self' 'unsafe-inline'",
    "worker-src 'self' blob:",
  ].join("; ");
}
