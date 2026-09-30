/**
 * The badge beside a team's name.
 *
 * A reader recognises a flag faster than they parse a name, and on a
 * hundred-fixture card that difference is most of the page's ergonomics.
 *
 * Two kinds, because football has two kinds of team. National sides get
 * their flag, which is derivable from the name and needs no licensing. Clubs
 * get a tinted disc with their initials, because club crests are per-club
 * artwork we have no licensed source for and no identifier to fetch one with
 * — one team row in eight hundred and eighty carries an `api_football_id`.
 *
 * The monogram is deliberately a monogram rather than a generic ball or
 * shield icon. It is obviously a placeholder, it is different per club so
 * the column still helps you scan, and it can never show the wrong badge.
 *
 * Flags come from flagcdn, which is free, keyless and does not track. The
 * URL is built in one place so swapping it for vendored SVGs later is a
 * one-line change.
 */

import type { Badge } from "@/lib/board";

/** Swap this to move off the CDN. Nothing else references it. */
function flagSrc(code: string, width: 20 | 40 | 80) {
  return `https://flagcdn.com/w${width}/${code}.png`;
}

export function TeamCrest({
  badge,
  name,
  size = 20,
}: {
  badge: Badge | null | undefined;
  /** Used for the alt text, so a missing image still says who is playing. */
  name: string;
  size?: 18 | 20 | 28;
}) {
  const box = { width: size, height: size };

  if (badge?.kind === "flag" && badge.code) {
    return (
      // Flags are wider than they are tall; the box is square and the image
      // covers it, so a row of them lines up regardless of aspect ratio.
      <span
        className="inline-flex shrink-0 items-center justify-center overflow-hidden rounded-[3px] bg-[var(--color-surface-raised)]"
        style={box}
      >
        <img
          src={flagSrc(badge.code, size > 20 ? 40 : 20)}
          srcSet={`${flagSrc(badge.code, size > 20 ? 80 : 40)} 2x`}
          alt=""
          width={size}
          height={size}
          loading="lazy"
          decoding="async"
          className="h-full w-full object-cover"
        />
        <span className="sr-only">{name}</span>
      </span>
    );
  }

  return (
    <span
      aria-hidden
      title={name}
      className="inline-flex shrink-0 items-center justify-center rounded-full border border-[var(--color-line-strong)] bg-[var(--color-surface-raised)] font-semibold text-[var(--color-text-faint)]"
      style={{ ...box, fontSize: size <= 20 ? 8.5 : 11 }}
    >
      {badge?.initials ?? "?"}
    </span>
  );
}
