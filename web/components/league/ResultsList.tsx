/**
 * The latest results on record, plain.
 *
 * No pick is shown beside them. A result we never priced has no call to
 * grade, and showing the engine's retrospective view of it here would be a
 * backtest wearing the clothes of a forecast. Where a graded call exists it
 * lives on the match's own page.
 */

import Link from "next/link";
import type { LeagueResult } from "@/lib/discover";

function day(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function ResultsList({ results }: { results: LeagueResult[] }) {
  return (
    <ul className="overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)]">
      {results.map((r, index) => (
        <li
          key={r.match_id}
          className={index > 0 ? "border-t border-[var(--color-line)]" : ""}
        >
          <Link
            href={`/match/${r.match_id}`}
            className="grid grid-cols-[96px_1fr_auto_1fr] items-center gap-3 px-4 py-2.5 text-[13px] transition-colors hover:bg-[var(--color-surface-raised)]"
          >
            <span className="text-[12px] text-[var(--color-text-faint)] tabular-nums">
              {day(r.match_date)}
            </span>
            <span className="truncate text-right">{r.home_team}</span>
            <span className="min-w-[44px] text-center font-semibold tabular-nums">
              {r.home_score}&ndash;{r.away_score}
            </span>
            <span className="truncate">{r.away_team}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
