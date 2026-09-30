/**
 * Head-to-head: every completed meeting between these two sides this
 * engine has on record.
 *
 * Sourced from `GET /matches?team=&opponent=`, which matches either side
 * regardless of who was at home in a given meeting — the tally below counts
 * a win for whichever of the two teams actually won, not "home wins".
 */

import Link from "next/link";
import type { MatchSummary } from "@/lib/types";

export function H2HPanel({
  meetings,
  home,
  away,
}: {
  meetings: MatchSummary[];
  home: string;
  away: string;
}) {
  if (meetings.length === 0) return null;

  let homeWins = 0;
  let draws = 0;
  let awayWins = 0;
  for (const m of meetings) {
    if (m.home_score === null || m.away_score === null) continue;
    const homeIsHomeSide = m.home_team === home;
    const homeGoals = homeIsHomeSide ? m.home_score : m.away_score;
    const awayGoals = homeIsHomeSide ? m.away_score : m.home_score;
    if (homeGoals > awayGoals) homeWins += 1;
    else if (homeGoals === awayGoals) draws += 1;
    else awayWins += 1;
  }
  const total = homeWins + draws + awayWins;

  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
      <h2 className="text-[15px] font-semibold">Head to head</h2>
      <p className="mt-1 mb-5 text-[13px] text-[var(--color-text-dim)]">
        The last {total} meeting{total === 1 ? "" : "s"} on record.
      </p>

      {total > 0 && (
        <div className="mb-5 flex h-2 w-full overflow-hidden rounded-full bg-[var(--color-line)]">
          <div
            style={{
              flexGrow: Math.max(homeWins, 0.02),
              background: "var(--color-home)",
            }}
          />
          <div
            style={{
              flexGrow: Math.max(draws, 0.02),
              background: "var(--color-draw)",
            }}
          />
          <div
            style={{
              flexGrow: Math.max(awayWins, 0.02),
              background: "var(--color-away)",
            }}
          />
        </div>
      )}
      <div className="mb-6 flex justify-between text-[13px] text-[var(--color-text-dim)]">
        <span>
          <b className="text-[var(--color-text)]">{homeWins}</b> {home} wins
        </span>
        <span>
          <b className="text-[var(--color-text)]">{draws}</b> draws
        </span>
        <span>
          <b className="text-[var(--color-text)]">{awayWins}</b> {away} wins
        </span>
      </div>

      <ul className="space-y-2">
        {meetings.map((m) => {
          let accent = "var(--color-line-strong)";
          if (m.home_score !== null && m.away_score !== null) {
            const homeIsHomeSide = m.home_team === home;
            const homeGoals = homeIsHomeSide ? m.home_score : m.away_score;
            const awayGoals = homeIsHomeSide ? m.away_score : m.home_score;
            accent =
              homeGoals > awayGoals
                ? "var(--color-won)"
                : homeGoals === awayGoals
                  ? "var(--color-unknown)"
                  : "var(--color-lost)";
          }
          return (
            <li key={m.match_id}>
              <Link
                href={`/match/${m.match_id}`}
                className="flex items-center gap-3 rounded-[var(--radius-md)] border-l-[3px] py-1.5 pr-2 pl-2.5 text-[13px] transition-colors hover:bg-[var(--color-surface-raised)]"
                style={{ borderLeftColor: accent }}
              >
                <span className="text-[var(--color-text-faint)]">
                  {new Date(m.match_date).toLocaleDateString(undefined, {
                    year: "numeric",
                    month: "short",
                    day: "numeric",
                  })}
                </span>
                <span className="min-w-0 flex-1 truncate font-medium">
                  {m.home_team}{" "}
                  <span className="font-normal text-[var(--color-text-faint)]">
                    v
                  </span>{" "}
                  {m.away_team}
                </span>
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
    </section>
  );
}
