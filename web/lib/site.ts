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

export const SITE_NAME = "SARDASPORTS";

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

/**
 * Who runs the site and how to reach them, read from the environment and shown
 * only when set. A privacy policy and an About page that name a person or
 * company have to name the real one, so these are never given a default: while
 * they are unset the pages say "the site's operator" and point to the Contact
 * form, which works without either.
 */
export const OPERATOR_NAME =
  process.env.NEXT_PUBLIC_OPERATOR_NAME?.trim() || null;
export const CONTACT_EMAIL =
  process.env.NEXT_PUBLIC_CONTACT_EMAIL?.trim() || null;

/**
 * Where readers can reach the operator outside the Contact form, shown in the
 * footer's "Reach us" block. Each is `null` until the real value is supplied, and a
 * null renders as "Coming soon" with no link: a link is never built from a made-up
 * number or handle.
 *
 * - `whatsapp`: the number in international format, digits only (e.g. "2348012345678")
 * - `telegram`: the username, without the "@"
 * - `x`: the handle, without the "@"
 *
 * The email shown beside them is `CONTACT_EMAIL` above, so the footer, the Contact
 * page and the privacy policy always name the same address.
 */
export const SOCIAL_CONTACTS: {
  whatsapp: string | null;
  telegram: string | null;
  x: string | null;
} = {
  whatsapp: "447741807953",
  telegram: null,
  x: null,
};
