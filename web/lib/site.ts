/**
 * Where this site lives, and whether it may be indexed.
 *
 * Every canonical URL, sitemap entry and social-share link is built from the
 * public address, so it has to be real. It is read from NEXT_PUBLIC_SITE_URL,
 * set once at deploy time (for example https://www.example.com). Until it is
 * set, the site assumes it is a local or staging copy and tells search engines
 * to stay away: a staging site that gets indexed competes with the real one and
 * is slow to forget.
 */

export const SITE_NAME = "UniquePredict";

const configured = process.env.NEXT_PUBLIC_SITE_URL?.trim();

/** The public origin, without a trailing slash. */
export const SITE_URL = (configured || "http://localhost:3000").replace(
  /\/+$/,
  "",
);

/** True only once a real, public address has been configured. */
export const IS_LIVE_SITE =
  Boolean(configured) && !/localhost|127\.0\.0\.1|\.local\b/i.test(configured!);

export function absoluteUrl(path = "/"): string {
  return `${SITE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}
