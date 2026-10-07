/**
 * What crawlers may fetch.
 *
 * Until a real public address is configured (NEXT_PUBLIC_SITE_URL, see
 * lib/site.ts) the answer is nothing: a local or staging copy that gets indexed
 * competes with the real site and is slow to be forgotten. Once the site is live
 * everything is open and the sitemap is announced.
 *
 * Pages that should not rank (the legacy prediction board, the model analytics
 * view) are marked noindex on the page rather than blocked here, because a crawler
 * has to be allowed to fetch a page to see that it says noindex.
 */

import type { MetadataRoute } from "next";
import { absoluteUrl, IS_LIVE_SITE, SITE_URL } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  if (!IS_LIVE_SITE) {
    return { rules: { userAgent: "*", disallow: "/" } };
  }
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: absoluteUrl("/sitemap.xml"),
    host: SITE_URL,
  };
}
