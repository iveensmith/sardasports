/**
 * One match in play: its minute, the score so far, the two sides, and the engine's tip.
 *
 * The score shown is the live feed's, which is display-only and separate from the final
 * result everywhere else on the site (see `app/services/live_scores.py`). The tip is the
 * one stored before kick-off; while the match is in play it has no verdict, and this
 * does not invent one.
 */

import Link from "next/link";
import { TeamCrest } from "@/components/board/TeamCrest";
import type { BoardRow } from "@/lib/board";

export function LiveMatch({ row }: { row: BoardRow }) {
  const live = row.live;
  if (!live) return null;
  return (
    <Link
      href={`/match/${row.slug}`}
      prefetch={false}
      className="grid grid-cols-[56px_1fr_auto] items-center gap-3 rounded-[12px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] px-3 py-3 transition-colors hover:border-[var(--color-gold)]/60 sm:grid-cols-[64px_1fr_auto_auto]"
    >
      <span className="flex flex-col items-center gap-1">
        <span className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-lost)]/15 px-2 py-1 text-[12px] font-extrabold tracking-wide text-[var(--color-lost)] tabular-nums">
          <span
            aria-hidden
            className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--color-lost)] motion-reduce:animate-none"
          />
          {live.label}
        </span>
      </span>

      <span className="min-w-0 space-y-1.5 text-[14px] font-semibold">
        <span className="flex items-center gap-2.5">
          <TeamCrest badge={row.home_badge} name={row.home_team} size={20} />
          <span className="truncate">{row.home_team}</span>
        </span>
        <span className="flex items-center gap-2.5">
          <TeamCrest badge={row.away_badge} name={row.away_team} size={20} />
          <span className="truncate">{row.away_team}</span>
        </span>
      </span>

      <span className="flex flex-col items-center text-[18px] leading-tight font-black tabular-nums">
        <span>{live.home}</span>
        <span>{live.away}</span>
      </span>

      {row.best_tip && (
        <span className="col-span-3 flex items-center justify-between gap-2 border-t border-[var(--color-line)] pt-2 text-[12.5px] text-[var(--color-text-dim)] sm:col-span-1 sm:block sm:border-t-0 sm:pt-0 sm:text-right">
          <span className="truncate">
            {row.competition.short_name || row.competition.name}
          </span>
          <span className="block text-[12.5px] font-semibold text-[var(--color-gold-bright)] sm:mt-0.5">
            Tip: {row.best_tip.short_label} ·{" "}
            {Math.round(row.best_tip.probability)}%
          </span>
        </span>
      )}
    </Link>
  );
}
