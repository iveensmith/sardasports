/**
 * Match browser — the way into the 144,000 matches behind the predictions.
 *
 * Filters live in one row above the list and are driven by the URL, so a
 * filtered view is linkable and survives a refresh. Next 16: `searchParams`
 * is a Promise and must be awaited.
 *
 * Results are a dense list for the same reason the board is: these rows are
 * scanned and compared, and a card grid makes the eye re-anchor on each one.
 */

import Link from "next/link";
import { getCompetitions, getMatches } from "@/lib/api";
import type { Competition, MatchSummary } from "@/lib/types";

export const revalidate = 300;

export const metadata = {
  title: "Matches — UniquePredict",
};

const SPORTS = ["football", "basketball", "tennis"] as const;
const PAGE_SIZE = 50;

function Score({ match }: { match: MatchSummary }) {
  if (match.home_score === null || match.away_score === null) {
    return (
      <span className="text-[13px] text-[var(--color-text-faint)]">
        {match.status === "scheduled" ? "Upcoming" : "—"}
      </span>
    );
  }
  return (
    <span className="text-[15px] font-semibold">
      {match.home_score}
      <span className="mx-1.5 text-[var(--color-text-faint)]">–</span>
      {match.away_score}
    </span>
  );
}

function FilterBar({
  competitions,
  sport,
  competition,
  status,
}: {
  competitions: Competition[];
  sport: string;
  competition: string;
  status: string;
}) {
  // A plain GET form: no client JS needed, and the resulting URL is the
  // shareable state. Submitting resets to page one by omitting `offset`.
  return (
    <form
      className="mb-6 flex flex-wrap items-end gap-3"
      action="/matches"
      method="get"
    >
      <label className="flex flex-col gap-1.5">
        <span className="text-[12px] text-[var(--color-text-faint)]">Sport</span>
        <select
          name="sport"
          defaultValue={sport}
          className="min-w-[10rem] rounded-[var(--radius-md)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] px-3 py-2 text-[14px]"
        >
          <option value="">All sports</option>
          {SPORTS.map((s) => (
            <option key={s} value={s}>
              {s[0].toUpperCase() + s.slice(1)}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-[12px] text-[var(--color-text-faint)]">
          Competition
        </span>
        <select
          name="competition"
          defaultValue={competition}
          className="min-w-[16rem] rounded-[var(--radius-md)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] px-3 py-2 text-[14px]"
        >
          <option value="">All competitions</option>
          {competitions.map((c) => (
            <option key={`${c.sport}-${c.competition}`} value={c.competition}>
              {c.competition} ({c.match_count.toLocaleString()})
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="text-[12px] text-[var(--color-text-faint)]">
          Status
        </span>
        <select
          name="status"
          defaultValue={status}
          className="min-w-[9rem] rounded-[var(--radius-md)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] px-3 py-2 text-[14px]"
        >
          <option value="">Any</option>
          <option value="scheduled">Upcoming</option>
          <option value="completed">Completed</option>
        </select>
      </label>

      <button
        type="submit"
        className="rounded-[var(--radius-md)] border border-[var(--color-line-strong)] px-4 py-2 text-[14px] font-medium transition-colors hover:border-[var(--color-text-faint)]"
      >
        Apply filters
      </button>
    </form>
  );
}

export default async function MatchesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const first = (key: string) => {
    const value = params[key];
    return (Array.isArray(value) ? value[0] : value) ?? "";
  };

  const sport = first("sport");
  const competition = first("competition");
  const status = first("status");
  const offset = Number(first("offset")) || 0;

  let matches: MatchSummary[] = [];
  let competitions: Competition[] = [];
  let total = 0;
  let error: string | null = null;

  try {
    const [matchResult, competitionResult] = await Promise.all([
      getMatches({
        sport: sport || undefined,
        competition: competition || undefined,
        status: status || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
      getCompetitions(sport || undefined),
    ]);
    matches = matchResult.matches;
    total = matchResult.count;
    competitions = competitionResult.competitions;
  } catch (e) {
    error = e instanceof Error ? e.message : "The engine could not be reached.";
  }

  const query = new URLSearchParams();
  if (sport) query.set("sport", sport);
  if (competition) query.set("competition", competition);
  if (status) query.set("status", status);
  const pageHref = (newOffset: number) => {
    const next = new URLSearchParams(query);
    if (newOffset > 0) next.set("offset", String(newOffset));
    return `/matches${next.toString() ? `?${next}` : ""}`;
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <header className="mb-7">
        <h1 className="text-[32px] font-bold tracking-[-0.02em]">Matches</h1>
        <p className="mt-2 max-w-[62ch] text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          Everything the engine has ingested — football, basketball and tennis.
          Open any match for its full prediction.
        </p>
      </header>

      <FilterBar
        competitions={competitions}
        sport={sport}
        competition={competition}
        status={status}
      />

      {error ? (
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[15px] font-medium">The engine is unreachable</p>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">{error}</p>
        </div>
      ) : matches.length === 0 ? (
        <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-8">
          <p className="text-[15px] font-medium">Nothing matches those filters</p>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">
            Try a different competition, or clear the status filter.
          </p>
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)]">
            <div className="px-4 py-3 text-[13px] text-[var(--color-text-dim)]">
              {total.toLocaleString()} match{total === 1 ? "" : "es"}
              {total > PAGE_SIZE && (
                <span className="text-[var(--color-text-faint)]">
                  {" "}
                  · showing {offset + 1}–
                  {Math.min(offset + PAGE_SIZE, total)}
                </span>
              )}
            </div>

            {matches.map((match) => (
              <Link
                key={match.match_id}
                href={`/match/${match.match_id}`}
                className="grid grid-cols-[1fr_auto] items-center gap-x-5 gap-y-1 border-t border-[var(--color-line)] px-4 py-3.5 transition-colors hover:bg-[var(--color-surface-raised)] md:grid-cols-[7rem_minmax(0,1fr)_auto]"
              >
                <div className="text-[13px] text-[var(--color-text-dim)]">
                  {new Date(match.match_date).toLocaleDateString(undefined, {
                    year: "numeric",
                    month: "short",
                    day: "numeric",
                  })}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-[15px]">
                    {match.home_team}{" "}
                    <span className="text-[var(--color-text-faint)]">v</span>{" "}
                    {match.away_team}
                  </p>
                  <p className="mt-0.5 truncate text-[12px] text-[var(--color-text-faint)]">
                    {match.competition} · {match.season}
                  </p>
                </div>
                <div className="justify-self-end">
                  <Score match={match} />
                </div>
              </Link>
            ))}
          </div>

          <nav className="mt-5 flex items-center justify-between text-[14px]">
            {offset > 0 ? (
              <Link
                href={pageHref(Math.max(0, offset - PAGE_SIZE))}
                className="text-[var(--color-text-dim)] underline-offset-4 hover:text-[var(--color-text)] hover:underline"
              >
                Previous
              </Link>
            ) : (
              <span />
            )}
            {offset + PAGE_SIZE < total && (
              <Link
                href={pageHref(offset + PAGE_SIZE)}
                className="text-[var(--color-text-dim)] underline-offset-4 hover:text-[var(--color-text)] hover:underline"
              >
                Next
              </Link>
            )}
          </nav>
        </>
      )}
    </div>
  );
}
