import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A self-contained server (server.js plus only the modules it needs), which is what the
  // production Docker image runs. It does not change `next dev` or `next start`.
  output: "standalone",
  // Public pages carry nothing personal, so a CDN may keep a copy for a minute and serve a
  // stale one while it refreshes (the engine's data is cached for minutes already). Cloudflare
  // only caches HTML when a Cache Rule marks it eligible, so without that rule (see
  // docs/deployment.md) this changes nothing. The API routes, build assets and CSV downloads
  // are left alone.
  async headers() {
    return [
      {
        source: "/((?!api/|_next/|.*[.]csv$).*)",
        headers: [
          {
            key: "Cache-Control",
            value: "public, s-maxage=60, stale-while-revalidate=600",
          },
        ],
      },
    ];
  },
  experimental: {
    // Off, not the default `true`. This cache sits in front of every fetch
    // — including ones with `cache: "no-store"` — and only clears on a
    // browser navigation, not on a plain HTTP request. That combination
    // cost real time this session: the engine's board changes constantly
    // (new predictions, new odds, newly-graded results), and every check
    // that wasn't a fresh browser navigation kept seeing an old snapshot
    // long after the underlying bug it reflected was already fixed.
    serverComponentsHmrCache: false,
  },
};

export default nextConfig;
