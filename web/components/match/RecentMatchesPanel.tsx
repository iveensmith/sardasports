/**
 * Each side's own recent results, independent of each other and of any
 * head-to-head history — this is "how have they been playing", not "how
 * have they done against this opponent" (see `H2HPanel` for that).
 */

import Link from "next/link";
import type { RecentMatch } from "@/lib/types";

function resultFor(m: RecentMatch, team: string): "W" | "D" | "L" | null {
  if (m.home_score === null || m.away_score === null) return null;
  const isHome = m.home_team === team;
  const scored = isHome ? m.home_score : m.away_score;
  const conceded = isHome ? m.away_score : m.home_score;
  if (scored > conceded) return "W";
  if (scored === conceded) return "D";
  return "L";
}

const RESULT_COLOR: Record<"W" | "D" | "L", string> = {
  W: "var(--color-won)",
  D: "var(--color-unknown)",
  L: "var(--color-lost)",
};

function TeamRecentList({
  team,
  matches,
}: {
  team: string;
  matches: RecentMatch[];
}) {
  return (
    <div>
      <div className="mb-2.5 flex items-center gap-2">
        <h3 className="truncate text-[13.5px] font-semibold">{team}</h3>
        <span className="flex gap-1">
          {matches.map((m) => {
            const result = resultFor(m, team);
            if (!result) return null;
            return (
              <span
                key={m.match_id}
                className="flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-bold text-[var(--color-ink-on-accent)]"
                style={{ background: RESULT_COLOR[result] }}
              >
                {result}
              </span>
            );
          })}
        </span>
      </div>
      <ul className="space-y-1.5">
        {matches.map((m) => {
          const opponent = m.home_team === team ? m.away_team : m.home_team;
          const venue = m.home_team === team ? "H" : "A";
          return (
            <li key={m.match_id}>
              <Link
                href={`/match/${m.match_id}`}
                className="flex items-center justify-between gap-2 rounded-[var(--radius-md)] px-2 py-1.5 text-[12.5px] transition-colors hover:bg-[var(--color-surface-raised)]"
              >
                <span className="text-[var(--color-text-faint)]">{venue}</span>
                <span className="min-w-0 flex-1 truncate">{opponent}</span>
                <span className="font-semibold tabular-nums">
                  {m.home_score !== null
                    ? `${m.home_score}-${m.away_score}`
                    : "—"}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function RecentMatchesPanel({
  home,
  away,
  homeMatches,
  awayMatches,
}: {
  home: string;
  away: string;
  homeMatches: RecentMatch[];
  awayMatches: RecentMatch[];
}) {
  if (homeMatches.length === 0 && awayMatches.length === 0) return null;

  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
      <h2 className="mb-5 text-[15px] font-semibold">Recent matches</h2>
      <div className="grid gap-6 sm:grid-cols-2">
        <TeamRecentList team={home} matches={homeMatches} />
        <TeamRecentList team={away} matches={awayMatches} />
      </div>
    </section>
  );
}
