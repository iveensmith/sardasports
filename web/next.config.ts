import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A self-contained server (server.js plus only the modules it needs), which is what the
  // production Docker image runs. It does not change `next dev` or `next start`.
  output: "standalone",
  // Public pages carry nothing personal, so a CDN may keep a copy for a minute and serve a
  // stale one while it refreshes (the engine's data is cached for minutes already). Cloudflare
  // only caches HTML when a Cache Rule marks it eligible (see docs/deployment.md).
  //
  // Pages that depend on who is looking are NOT public, and say so: the account and admin
  // pages, the sign-in and sign-up forms, premium, the editor's picks and each blog post (a
  // premium post shows its body to members only). They are sent `private, no-store`, so no
  // shared cache, Cloudflare's included, can ever keep one member's view and give it to another.
  // The API routes, build assets, uploaded images and CSV downloads set their own headers.
  async headers() {
    const personal = [
      "/account/:path*",
      "/admin/:path*",
      "/login",
      "/signup",
      "/forgot-password",
      "/reset-password",
      "/verify-email",
      "/premium",
      "/picks",
      "/blog/:slug",
    ];
    return [
      {
        source:
          "/((?!$|api/|_next/|media/|ckeditor/|account|admin|login|signup|forgot-password|reset-password|verify-email|premium|picks|blog/.+|live|match|.*[.]csv$).*)",
        headers: [
          {
            key: "Cache-Control",
            value: "public, s-maxage=60, stale-while-revalidate=600",
          },
        ],
      },
      // Pages that show scores and kick-off states: a copy is kept for seconds, not minutes, so a
      // match that has started is not shown as waiting to start, and a score is not stale.
      {
        source: "/live",
        headers: [
          {
            key: "Cache-Control",
            value: "public, s-maxage=10, stale-while-revalidate=20",
          },
        ],
      },
      ...["/", "/matches", "/match/:id"].map((source) => ({
        source,
        headers: [
          {
            key: "Cache-Control",
            value: "public, s-maxage=30, stale-while-revalidate=60",
          },
        ],
      })),
      ...personal.map((source) => ({
        source,
        headers: [{ key: "Cache-Control", value: "private, no-store" }],
      })),
    ];
  },
  // `/basketball?date=2026-10-15` (links already in the wild, and the day strip) is answered by
  // `/basketball/d/2026-10-15`, a normal cacheable route. The visitor's address does not change.
  // An address with a date that is not YYYY-MM-DD does not match and shows today's page.
  async rewrites() {
    return ["basketball", "tennis"].map((sport) => ({
      source: `/${sport}`,
      has: [
        {
          type: "query" as const,
          key: "date",
          value: "(?<day>\\d{4}-\\d{2}-\\d{2})",
        },
      ],
      destination: `/${sport}/d/:day`,
    }));
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
