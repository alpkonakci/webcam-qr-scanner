import type { NextConfig } from "next";

export function buildContentSecurityPolicy(isDevelopment: boolean): string {
  const scriptSources = ["'self'", "'unsafe-inline'"];
  if (isDevelopment) {
    // React's development runtime uses eval for debugging and reconstructed
    // call stacks. Keep this exception local to `next dev`; Vercel production
    // builds retain the stricter policy below.
    scriptSources.push("'unsafe-eval'");
  }

  return [
    "default-src 'self'",
    "base-uri 'none'",
    "connect-src 'self'",
    "font-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "img-src 'self' data:",
    "manifest-src 'self'",
    "object-src 'none'",
    `script-src ${scriptSources.join(" ")}`,
    "style-src 'self' 'unsafe-inline'",
    "worker-src 'self' blob:",
  ].join("; ");
}

const nextConfig: NextConfig = {
  async headers() {
    const contentSecurityPolicy = buildContentSecurityPolicy(
      process.env.NODE_ENV === "development",
    );

    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          {
            key: "Permissions-Policy",
            value: "camera=(self), geolocation=(), microphone=()",
          },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default nextConfig;
