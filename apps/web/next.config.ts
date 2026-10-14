import path from "node:path";

import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

// One .env at the repo root serves both apps; only NEXT_PUBLIC_* values reach the browser.
loadEnvConfig(path.resolve(__dirname, "../.."));

const apiOrigin = (() => {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").origin;
  } catch {
    return "";
  }
})();

// docs/08 §2. Next.js injects inline bootstrap scripts, so script-src needs 'unsafe-inline'
// (no nonce pipeline on static pages); everything else is locked to self + the API.
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self' ${apiOrigin}`,
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          ...(process.env.NODE_ENV === "production"
            ? [
                { key: "Content-Security-Policy", value: csp },
                { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
              ]
            : []),
        ],
      },
    ];
  },
};

export default nextConfig;
