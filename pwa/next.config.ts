import type { NextConfig } from "next";
import { buildContentSecurityPolicy } from "./lib/content-security-policy.ts";
export { buildContentSecurityPolicy };

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
