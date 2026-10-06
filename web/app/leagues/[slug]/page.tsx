/**
 * One competition.
 *
 * Everything here is counted from the matches the engine holds for it, or is
 * the engine's own settled record for it. Two honesty rules shape the page:
 *
 * - **It says how current it is.** Most domestic competitions' newest result
 *   is months old, so the table and rates describe a past season. A banner
 *   states the date of the newest result instead of letting a table read as
 *   live, and "hot"/"cold" teams are only named when the data is recent
 *   enough for that to mean something.
 * - **The record keeps live and backtested apart**, as the track-record page
 *   does, because a win rate beside a league name reads as a promise.
 *
 * Next 16: `params` and `searchParams` are both Promises and must be awaited.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { BoardTable } from "@/components/board/BoardTable";
import { CountryMark } from "@/components/board/CountryMark";
import { FormCards } from "@/components/league/FormCards";
import { LeagueTabs, type LeagueTab } from "@/components/league/LeagueTabs";
import { RateBar } from "@/components/league/RateBar";
import { ResultsList } from "@/components/league/ResultsList";
import { StandingsTable } from "@/components/league/StandingsTable";
import { ProbabilitySplit } from "@/components/ProbabilitySplit";
import { EngineError, getLeague } from "@/lib/api";
import type { LeagueDetail } from "@/lib/discover";
import { rate } from "@/lib/progress";

export const revalidate = 600;

/** Past this, "recent" form and a "current" table would be misleading. */
const STALE_AFTER_DAYS = 45;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const league = await getLeague(slug).catch(() => null);
  if (!league) return { title: "League — UniquePredict" };
  return {
    title: `${league.competition} predictions — UniquePredict`,
    description: `${league.competition}: result and goals rates from ${league.history.matches.toLocaleString()} matches on record, the engine's own record in this competition, and its picks for upcoming fixtures.`,
  };
}

function longDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

function Tile({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-4">
      <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
        {label}
      </p>
      <p className="mt-1.5 text-[24px] leading-none font-bold tabular-nums">
        {value}
      </p>
      {note && (
        <p className="mt-1.5 text-[12px] leading-relaxed text-[var(--color-text-faint)]">
          {note}
        </p>
      )}
    </div>
  );
}

/** The two-line summary under the header, built only from what was counted. */
function summary(league: LeagueDetail): string {
  const h = league.history;
  if (h.matches === 0) {
    return `The engine holds no completed ${league.competition} matches yet, so there is nothing to report about it.`;
  }
  const parts = [
    `${league.competition} has ${h.matches.toLocaleString()} completed matches on record, from ${longDate(h.first!)} to ${longDate(h.last!)}.`,
    `Home sides won ${h.home_win?.toFixed(0)}% of them and ${h.draw?.toFixed(0)}% were drawn; ${h.over_2_5?.toFixed(0)}% had over 2.5 goals and both teams scored in ${h.btts?.toFixed(0)}%.`,
  ];
  const leader = league.standings[0];
  if (leader && league.season) {
    parts.push(
      `${leader.team} top the ${league.season} table on ${leader.points} points from ${leader.played} games.`,
    );
  }
  return parts.join(" ");
}

export default async function LeaguePage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { slug } = await params;
  const query = await searchParams;

  let league: LeagueDetail | null = null;
  let error: string | null = null;
  try {
    league = await getLeague(slug);
  } catch (e) {
    error =
      e instanceof EngineError || e instanceof Error
        ? e.message
        : "The engine could not be reached.";
  }

  if (error) {
    return (
      <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[15px] font-medium">The engine is unreachable</p>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">
            {error}
          </p>
        </div>
      </div>
    );
  }
  if (!league) notFound();

  const h = league.history;
  const hasTable = !league.is_international && league.standings.length > 0;
  const tabs: LeagueTab[] = hasTable
    ? ["predictions", "standings"]
    : ["predictions"];
  const requested = Array.isArray(query.tab) ? query.tab[0] : query.tab;
  const active: LeagueTab =
    requested === "standings" && hasTable ? "standings" : "predictions";

  const age = league.last_match_age_days;
  const stale = age === null || age > STALE_AFTER_DAYS;
  const { backtest, live } = league.record;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-10 sm:px-6 lg:px-10">
      <nav
        aria-label="Breadcrumb"
        className="text-[12.5px] text-[var(--color-text-faint)]"
      >
        <Link href="/leagues" className="hover:text-[var(--color-text)]">
          Leagues
        </Link>{" "}
        / <span className="text-[var(--color-text-dim)]">{league.country}</span>
      </nav>

      <header className="mt-4 max-w-[78ch]">
        <div className="flex items-center gap-3">
          <CountryMark code={league.country_code} />
          <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
            {league.country}
            {league.tier === 2 ? " · 2nd tier" : ""}
          </p>
        </div>
        <h1 className="mt-2.5 text-[clamp(1.9rem,4.5vw,2.6rem)] leading-tight font-bold tracking-[-0.02em]">
          {league.competition}
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          {summary(league)}
        </p>
      </header>

      {stale && (
        <div
          className="mt-6 rounded-[var(--radius-lg)] border p-5"
          style={{ borderColor: "var(--color-gold-dim)" }}
        >
          <p
            className="text-[14px] font-semibold"
            style={{ color: "var(--color-gold-bright)" }}
          >
            {h.last
              ? `The newest result on record here is from ${longDate(h.last)}.`
              : "There are no results on record for this competition yet."}
          </p>
          {h.last && age !== null && (
            <p className="mt-2 max-w-[72ch] text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
              That is {age.toLocaleString()} days ago, so the rates, the table
              and the record below describe that period, not the current season.
              Fixtures and picks appear here once the competition is being
              ingested again.
            </p>
          )}
        </div>
      )}

      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile
          label="Matches on record"
          value={h.matches.toLocaleString()}
          note={h.first ? `since ${h.first.slice(0, 4)}` : undefined}
        />
        <Tile
          label={league.season ? `Teams, ${league.season}` : "Teams"}
          value={league.teams !== null ? String(league.teams) : "—"}
          note={
            league.is_international
              ? "A national-team competition has no fixed set of clubs"
              : undefined
          }
        />
        <Tile
          label="Backtested here"
          value={backtest.settled > 0 ? rate(backtest) : "—"}
          note={
            backtest.settled > 0
              ? `${backtest.won} of ${backtest.settled} settled, graded after the match`
              : "No backtested calls in this competition"
          }
        />
        <Tile
          label="Live record here"
          value={live.settled > 0 ? rate(live) : "—"}
          note={
            live.settled > 0
              ? `${live.won} of ${live.settled} settled, stored before kick-off`
              : "No prediction here has yet been stored before kick-off"
          }
        />
      </div>

      {h.matches > 0 && (
        <section className="mt-8">
          <h2 className="text-[15px] font-semibold">
            How matches here tend to go
          </h2>
          <p className="mt-1.5 text-[13px] text-[var(--color-text-faint)]">
            Across all {h.matches.toLocaleString()} completed matches on record.
          </p>

          <div className="mt-4 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
            <ProbabilitySplit
              home={h.home_win ?? 0}
              draw={h.draw ?? 0}
              away={h.away_win ?? 0}
              homeLabel="Home win"
              awayLabel="Away win"
            />
          </div>

          <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <RateBar label="Over 1.5 goals" value={h.over_1_5} />
            <RateBar label="Over 2.5 goals" value={h.over_2_5} />
            <RateBar label="Over 3.5 goals" value={h.over_3_5} />
            <RateBar label="Both teams score" value={h.btts} />
          </div>
        </section>
      )}

      {league.hot_team && league.cold_team && (
        <div className="mt-8">
          <FormCards
            hot={league.hot_team}
            cold={league.cold_team}
            window={league.form_window}
          />
        </div>
      )}

      <div className="mt-10">
        <LeagueTabs slug={league.slug} active={active} tabs={tabs} />

        <div className="pt-6">
          {active === "standings" ? (
            <>
              <p className="mb-3 text-[13px] text-[var(--color-text-faint)]">
                {league.season} season, from results through{" "}
                {h.last ? longDate(h.last) : "the newest on record"}. Computed
                from the results the engine holds.
              </p>
              <StandingsTable rows={league.standings} />
            </>
          ) : (
            <>
              <h2 className="text-[15px] font-semibold">Upcoming fixtures</h2>
              {league.fixtures.length > 0 ? (
                <div className="mt-3">
                  <BoardTable rows={league.fixtures} />
                </div>
              ) : (
                <p className="mt-2 max-w-[72ch] text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
                  No upcoming {league.short_name} fixtures are in the
                  engine&rsquo;s database right now. That reflects what has been
                  ingested, not what is scheduled to be played.
                </p>
              )}

              {league.results.length > 0 && (
                <>
                  <h2 className="mt-8 text-[15px] font-semibold">
                    Latest results on record
                  </h2>
                  <div className="mt-3">
                    <ResultsList results={league.results} />
                  </div>
                </>
              )}

              <p className="mt-6 text-[13px]">
                <Link
                  href={`/matches?competition=${encodeURIComponent(league.competition)}`}
                  className="text-[var(--color-gold-bright)] hover:underline"
                >
                  Browse any day&rsquo;s board for {league.short_name} &rarr;
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
