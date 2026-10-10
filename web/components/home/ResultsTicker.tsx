/**
 * The settled-results strip under the hero.
 *
 * Constant motion, so it is linear — an eased marquee visibly slows and
 * speeds at the loop seam, which is the one place a reader notices it. It
 * pauses on hover and on focus-within, so nothing scrolls away from someone
 * trying to read or tab to it, and `prefers-reduced-motion` stops it dead
 * rather than slowing it down: a strip that crawls is worse for motion
 * sensitivity than one that sits still.
 *
 * The animation is a CSS keyframe rather than a spring or a JS loop. It runs
 * off the main thread and never needs to be interrupted or retargeted — this
 * is exactly the case keyframes are for, and the case a transition is not.
 *
 * Both edges are masked so items arrive and leave by fading rather than being
 * sliced by a hard boundary.
 *
 * It carries settled results only. A ticker of upcoming picks would be
 * advertising; a ticker of graded ones is the argument the site is making,
 * scrolling.
 */

import Link from "next/link";
import { MIN_STRIP_ITEMS } from "@/lib/api";
import type { BoardRow } from "@/lib/board";

function Item({ row }: { row: BoardRow }) {
  const tip = row.best_tip;
  if (!tip || tip.outcome === null || tip.outcome === "void") return null;
  const won = tip.outcome === "won";

  return (
    <li className="shrink-0">
      <Link
        href={`/match/${row.slug}`}
        className="flex items-center gap-2.5 rounded-[var(--radius-md)] px-3.5 py-2 text-[13px] whitespace-nowrap transition-colors hover:bg-[var(--color-surface)]"
      >
        <span className="text-[var(--color-text-dim)]">
          {row.home_team}
          <span className="mx-1.5 text-[var(--color-text-faint)]">v</span>
          {row.away_team}
        </span>
        <span
          className="font-semibold"
          style={{ color: won ? "var(--color-won)" : "var(--color-lost)" }}
        >
          {tip.short_label}
          {/* Colour is never the only carrier of a verdict. */}
          <span aria-hidden className="ml-1 text-[11px]">
            {won ? "✓" : "✕"}
          </span>
          <span className="sr-only">{won ? " (won)" : " (lost)"}</span>
        </span>
      </Link>
    </li>
  );
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

export function ResultsTicker({
  rows,
  from,
  to,
  minProbability = null,
}: {
  rows: BoardRow[];
  /** First and last match date the strip covers, named so it is never read as
   * last night's results when it is not. */
  from: string | null;
  to: string | null;
  /** Set when the strip only carries tips rated at least this likely. */
  minProbability?: number | null;
}) {
  const settled = rows.filter(
    (row) =>
      row.best_tip?.outcome === "won" || row.best_tip?.outcome === "lost",
  );
  // Below a handful the loop is more gap than content and reads as broken.
  if (settled.length < MIN_STRIP_ITEMS) return null;

  const won = settled.filter((r) => r.best_tip!.outcome === "won").length;

  return (
    <section
      aria-label="Recently settled picks"
      className="border-y border-[var(--color-line)] bg-[var(--color-surface)]/40 py-3"
    >
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10">
        {/* The dates are named rather than implied. These are the newest picks
            that settled, which is not necessarily last night's. */}
        <p className="mb-2 text-[12px] text-[var(--color-text-faint)]">
          {minProbability ? "Recent strong tips" : "Recently settled"}
          {from && to
            ? from === to
              ? `, ${shortDate(to)}`
              : `, ${shortDate(from)} to ${shortDate(to)}`
            : ""}
          : {won} of {settled.length} picks came in
          {minProbability ? ` (tips rated ${minProbability}% or more)` : ""}
        </p>
      </div>

      <div className="nt-marquee">
        {/* The track is duplicated so the loop has no seam. The copy is
            hidden from assistive tech, which would otherwise read every
            result twice. */}
        <ul className="nt-marquee__track">
          {settled.map((row) => (
            <Item key={row.match_id} row={row} />
          ))}
        </ul>
        <ul className="nt-marquee__track" aria-hidden>
          {settled.map((row) => (
            <Item key={`dup-${row.match_id}`} row={row} />
          ))}
        </ul>
      </div>
    </section>
  );
}
