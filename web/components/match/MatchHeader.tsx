/**
 * The match page's header card: both sides, the score or kickoff time, the
 * 1X2 price, and the half-time score where there is one.
 *
 * The fixture page carried none of this before — no score, no status, no
 * price — even though the board row linking to it shows all three. Reusing
 * that same "what's actually true right now" data here, rather than only
 * the prediction, is what makes this a match page and not just a prediction
 * printout.
 */

import Link from "next/link";
import type { Badge } from "@/lib/board";
import { teamSlug } from "@/lib/teams";
import type { MatchScore, Odds1X2 } from "@/lib/types";
import { TeamCrest } from "@/components/board/TeamCrest";

function OddsPill({ label, value }: { label: string; value: number | null }) {
  if (value === null) return null;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-line-strong)] px-2.5 py-1 text-[13px]">
      <span className="font-medium text-[var(--color-text-faint)]">
        {label}
      </span>
      <span className="font-semibold tabular-nums">{value.toFixed(2)}</span>
    </span>
  );
}

export function MatchHeader({
  home,
  away,
  homeBadge,
  awayBadge,
  competition,
  kickoff,
  status,
  score,
  htScore,
  odds,
  teamLinks = false,
}: {
  home: string;
  away: string;
  homeBadge: Badge | null;
  awayBadge: Badge | null;
  competition: string;
  kickoff: string;
  status: string;
  score: MatchScore | null;
  htScore: MatchScore | null;
  odds: Odds1X2 | null;
  /** Link each side to its team page. Football only: those pages hold clubs
   * and national sides, not tennis players. */
  teamLinks?: boolean;
}) {
  const finished = status === "completed";

  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
      <p className="text-[12.5px] text-[var(--color-text-faint)]">
        {competition}
      </p>

      <div className="mt-4 grid grid-cols-[1fr_auto_1fr] items-center gap-4">
        <div className="flex flex-col items-center gap-2.5 text-center">
          <TeamCrest badge={homeBadge} name={home} size={48} />
          {teamLinks ? (
            <Link
              href={`/teams/${teamSlug(home)}`}
              className="text-[15px] leading-tight font-semibold hover:text-[var(--color-gold-bright)]"
            >
              {home}
            </Link>
          ) : (
            <span className="text-[15px] leading-tight font-semibold">
              {home}
            </span>
          )}
        </div>

        <div className="flex flex-col items-center gap-1.5">
          {score ? (
            <p className="text-[34px] leading-none font-bold tabular-nums">
              {score.home}
              <span className="mx-1.5 text-[var(--color-text-faint)]">
                &ndash;
              </span>
              {score.away}
            </p>
          ) : (
            <p className="text-[15px] font-semibold tabular-nums">{kickoff}</p>
          )}
          <span
            className="text-[11px] font-semibold tracking-wider uppercase"
            style={{
              color: finished
                ? "var(--color-text-faint)"
                : "var(--color-gold-bright)",
            }}
          >
            {finished ? "Finished" : "Scheduled"}
          </span>
          {htScore && (
            <span className="text-[11.5px] text-[var(--color-text-faint)]">
              HT {htScore.home}&ndash;{htScore.away}
            </span>
          )}
        </div>

        <div className="flex flex-col items-center gap-2.5 text-center">
          <TeamCrest badge={awayBadge} name={away} size={48} />
          {teamLinks ? (
            <Link
              href={`/teams/${teamSlug(away)}`}
              className="text-[15px] leading-tight font-semibold hover:text-[var(--color-gold-bright)]"
            >
              {away}
            </Link>
          ) : (
            <span className="text-[15px] leading-tight font-semibold">
              {away}
            </span>
          )}
        </div>
      </div>

      {odds &&
        (odds.home !== null || odds.draw !== null || odds.away !== null) && (
          <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
            <OddsPill label="1" value={odds.home} />
            <OddsPill label="X" value={odds.draw} />
            <OddsPill label="2" value={odds.away} />
          </div>
        )}
    </section>
  );
}
