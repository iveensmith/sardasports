import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
