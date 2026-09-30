/**
 * Match detail.
 *
 * Renders whichever shape the engine returned. The three sports are not
 * variations on one layout with fields blanked out — a tennis match has no
 * expected goals and a basketball game has no draw, so each gets its own
 * body and the union is narrowed once, here.
 *
 * Split into tabs (see `MatchTabs`), each fetching only what it needs: the
 * prediction itself loads on every visit, but a team's form, head-to-head
 * history and recent results are each a further engine call that only
 * happens when a reader actually opens that tab.
 *
 * Next 16: `params` and `searchParams` are both Promises and must be awaited.
 */

import Link from "next/link";
import { notFound } from "next/navigation";
import { EngineError, getMatches, getPrediction, getTeam } from "@/lib/api";
import { matchIdFromSlug } from "@/lib/board";
import {
  HeadlineCall,
  MarketCallTable,
  ValuePanel,
} from "@/components/MarketCalls";
import {
  competitors,
  isBasketball,
  isFootball,
  isTennis,
  type Prediction,
} from "@/lib/types";
import { ProbabilitySplit } from "@/components/ProbabilitySplit";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { MarketTable } from "@/components/MarketTable";
import { EstimatorBreakdown } from "@/components/EstimatorSplit";
import { agreementFrom } from "@/lib/agreement";
import { MatchHeader } from "@/components/match/MatchHeader";
import { GoalTimeline } from "@/components/match/GoalTimeline";
import { StatsComparison } from "@/components/match/StatsComparison";
import { SeasonStatsPanel } from "@/components/match/SeasonStatsPanel";
import { FormPanel } from "@/components/match/FormPanel";
import { H2HPanel } from "@/components/match/H2HPanel";
import { RecentMatchesPanel } from "@/components/match/RecentMatchesPanel";
import { MatchTabs, type MatchTab } from "@/components/match/MatchTabs";

export const revalidate = 60;

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-surface)] px-4 py-3">
      <p className="text-[12px] text-[var(--color-text-faint)]">{label}</p>
      <p className="mt-1 text-[22px] leading-none font-semibold">{value}</p>
    </div>
  );
}

function FootballBody({
  p,
}: {
  p: Extract<Prediction, { sport: "football" }>;
}) {
  const { home, away } = competitors(p);
  return (
    <>
      {p.calls?.headline && <HeadlineCall call={p.calls.headline} />}

      <div className="mt-4 grid gap-4 md:grid-cols-[1.6fr_1fr]">
        <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
          <h2 className="mb-4 text-[15px] font-semibold">Outcome</h2>
          <ProbabilitySplit
            home={p.home_win}
            away={p.away_win}
            draw={p.draw}
            homeLabel={home}
            awayLabel={away}
          />
        </section>
        <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
          <ConfidenceMeter value={p.confidence} label={p.confidence_label} />
        </section>
      </div>

      <section className="mt-4 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
        <EstimatorBreakdown
          agreement={agreementFrom(p)}
          homeLabel={home}
          awayLabel={away}
        />
      </section>

      {/* The tables that follow are the working; the headline call above is
          the conclusion. */}
      {p.calls && p.calls.by_market.length > 0 && (
        <div className="mt-4">
          <MarketCallTable calls={p.calls.by_market} />
        </div>
      )}

      {/* The market comparison, moved off the board row. A different subject
          from the prediction, and one that needs room to be honest about
          what a large expected value usually means. */}
      {p.value && (
        <div className="mt-4">
          <ValuePanel value={p.value} />
        </div>
      )}

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Expected goals (home)" value={p.expected_goals_home} />
        <Stat label="Expected goals (away)" value={p.expected_goals_away} />
        <Stat label="Both teams score" value={`${p.btts_yes}%`} />
        <Stat
          label="Most likely score"
          value={p.top_scorelines[0]?.score ?? "—"}
        />
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <MarketTable
          title="Goals"
          markets={p.goals_markets}
          unavailableNote="This competition has no goal data the engine can price."
        />
        <MarketTable
          title="Half-time goals"
          markets={p.ht_goals_markets}
          unavailableNote="Half-time scores are not recorded for this competition."
        />
        <MarketTable
          title="Corners"
          markets={p.corners_markets}
          unavailableNote="This competition has no corner data, so these lines cannot be priced."
        />
        <MarketTable
          title="Cards"
          markets={p.cards_markets}
          unavailableNote="This competition has no card data, so these lines cannot be priced."
        />
      </div>

      {p.explanation && p.explanation.length > 0 && (
        <section className="mt-4 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
          <h3 className="text-[15px] font-semibold">What drove this</h3>
          <p className="mt-1 mb-4 text-[13px] text-[var(--color-text-dim)]">
            The features that moved the predicted outcome most, from the model
            itself rather than a written-after-the-fact rationale.
          </p>
          <ul className="space-y-2.5">
            {p.explanation.slice(0, 5).map((f) => {
              const positive = f.impact_percentage_points >= 0;
              const width = Math.min(
                Math.abs(f.impact_percentage_points) * 6,
                100,
              );
              return (
                <li key={f.feature} className="text-[13px]">
                  <div className="mb-1 flex justify-between gap-4">
                    <span className="truncate text-[var(--color-text-dim)]">
                      {f.feature.replace(/_/g, " ")}
                    </span>
                    <span>
                      {positive ? "+" : ""}
                      {f.impact_percentage_points.toFixed(1)} pts
                    </span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-[var(--color-line)]">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${width}%`,
                        background: positive
                          ? "var(--color-home)"
                          : "var(--color-away)",
                      }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </>
  );
}

function BasketballBody({
  p,
}: {
  p: Extract<Prediction, { sport: "basketball" }>;
}) {
  const { home, away } = competitors(p);
  return (
    <>
      <div className="grid gap-4 md:grid-cols-[1.6fr_1fr]">
        <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
          <h2 className="mb-4 text-[15px] font-semibold">Outcome</h2>
          <ProbabilitySplit
            home={p.home_win}
            away={p.away_win}
            homeLabel={home}
            awayLabel={away}
          />
        </section>
        <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
          <ConfidenceMeter value={p.confidence} label={p.confidence_label} />
        </section>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3">
        <Stat label="Expected points (home)" value={p.expected_points_home} />
        <Stat label="Expected points (away)" value={p.expected_points_away} />
        <Stat label="Expected total" value={p.expected_total_points} />
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <MarketTable
          title="Total points"
          markets={p.total_points_markets}
          unavailableNote="No trained model for these lines yet, and basketball has no statistical fallback."
        />
        <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5 text-[14px] leading-relaxed text-[var(--color-text-dim)]">
          <h3 className="mb-2 text-[15px] font-semibold text-[var(--color-text)]">
            No draw market
          </h3>
          Basketball plays overtime until someone wins — there were zero ties in
          the 4,149 games this model learned from, so the two probabilities
          above sum to 100 on their own.
        </section>
      </div>
    </>
  );
}

function TennisBody({ p }: { p: Extract<Prediction, { sport: "tennis" }> }) {
  const { home, away } = competitors(p);
  return (
    <>
      <div className="grid gap-4 md:grid-cols-[1.6fr_1fr]">
        <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
          <h2 className="mb-4 text-[15px] font-semibold">Outcome</h2>
          <ProbabilitySplit
            home={p.home_win}
            away={p.away_win}
            homeLabel={home}
            awayLabel={away}
          />
        </section>
        <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
          <ConfidenceMeter value={p.confidence} label={p.confidence_label} />
        </section>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Surface" value={p.surface ?? "—"} />
        <Stat label="Format" value={p.best_of ? `Best of ${p.best_of}` : "—"} />
        <Stat label="Expected total games" value={p.expected_total_games} />
        <Stat
          label="Rating gap (surface)"
          value={(p.elo_surface_home - p.elo_surface_away).toFixed(0)}
        />
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
          <h3 className="text-[15px] font-semibold">
            Rating, overall and on {p.surface ?? "this surface"}
          </h3>
          <p className="mt-1 mb-4 text-[13px] leading-relaxed text-[var(--color-text-dim)]">
            Clay ability is genuinely not grass ability, so the engine keeps a
            rating per surface. Where these two columns disagree, the surface
            one is the better guide.
          </p>
          <table className="w-full text-[14px]">
            <thead>
              <tr className="text-[12px] text-[var(--color-text-faint)]">
                <th className="pb-2 text-left font-medium">Player</th>
                <th className="pb-2 text-right font-medium">Overall</th>
                <th className="pb-2 text-right font-medium">Surface</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-[var(--color-line)]/60">
                <td className="py-2.5">{p.home_player}</td>
                <td className="py-2.5 text-right">{p.elo_home.toFixed(0)}</td>
                <td className="py-2.5 text-right">
                  {p.elo_surface_home.toFixed(0)}
                </td>
              </tr>
              <tr className="border-t border-[var(--color-line)]/60">
                <td className="py-2.5">{p.away_player}</td>
                <td className="py-2.5 text-right">{p.elo_away.toFixed(0)}</td>
                <td className="py-2.5 text-right">
                  {p.elo_surface_away.toFixed(0)}
                </td>
              </tr>
            </tbody>
          </table>
        </section>

        <MarketTable
          title="Total games"
          markets={p.total_games_markets}
          unavailableNote="No trained model for these lines yet."
        />
      </div>
    </>
  );
}

const VALID_TABS: MatchTab[] = [
  "tips",
  "season",
  "stats",
  "form",
  "h2h",
  "recent",
];

export default async function MatchPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  // Accepts both /match/144414 and the readable form the board links to,
  // /match/spain-vs-croatia-prediction-144414.
  const matchId = matchIdFromSlug(id);
  if (matchId === null) notFound();

  const rawTab = (await searchParams).tab;
  const requestedTab = Array.isArray(rawTab) ? rawTab[0] : rawTab;
  const tab: MatchTab = VALID_TABS.includes(requestedTab as MatchTab)
    ? (requestedTab as MatchTab)
    : "tips";

  let prediction: Prediction;
  try {
    prediction = await getPrediction(matchId);
  } catch (error) {
    if (error instanceof EngineError && error.status === 404) notFound();
    throw error;
  }

  const { home, away } = competitors(prediction);
  // Badges are football-only for now — basketball and tennis carry no
  // `home_badge`/`away_badge` fields, so this degrades to no crest rather
  // than a type error or a fabricated flag.
  const homeBadge = isFootball(prediction) ? prediction.home_badge : null;
  const awayBadge = isFootball(prediction) ? prediction.away_badge : null;

  // Every other tab is its own further engine call, made only when a reader
  // has actually asked for that tab rather than on every visit to the page.
  const [homeTeam, awayTeam] = ["season", "form", "recent"].includes(tab)
    ? await Promise.all([getTeam(home), getTeam(away)])
    : [null, null];
  const h2h =
    tab === "h2h"
      ? await getMatches({
          team: home,
          opponent: away,
          status: "completed",
          limit: 10,
        })
      : null;

  const tabs: MatchTab[] = isFootball(prediction)
    ? ["tips", "season", "stats", "form", "h2h", "recent"]
    : ["tips", "season", "form", "h2h", "recent"];

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 py-10">
      <Link
        href="/matches"
        className="text-[14px] text-[var(--color-text-dim)] underline-offset-4 hover:text-[var(--color-text)] hover:underline"
      >
        Back to matches
      </Link>

      <div className="mt-5">
        <MatchHeader
          home={home}
          away={away}
          homeBadge={homeBadge}
          awayBadge={awayBadge}
          competition={prediction.competition}
          kickoff={new Date(prediction.match_date).toLocaleString(undefined, {
            dateStyle: "full",
            timeStyle: "short",
          })}
          status={prediction.match_status}
          score={prediction.match_score}
          htScore={isFootball(prediction) ? prediction.ht_score : null}
          odds={prediction.odds_1x2}
        />
      </div>

      {isFootball(prediction) && prediction.events.length > 0 && (
        <div className="mt-4">
          <GoalTimeline
            events={prediction.events}
            home={home}
            away={away}
            homeBadge={homeBadge}
            awayBadge={awayBadge}
          />
        </div>
      )}

      <div className="mt-6">
        <MatchTabs matchId={matchId} active={tab} tabs={tabs} />
      </div>

      <div className="mt-6">
        {tab === "tips" && (
          <>
            {isFootball(prediction) && <FootballBody p={prediction} />}
            {isBasketball(prediction) && <BasketballBody p={prediction} />}
            {isTennis(prediction) && <TennisBody p={prediction} />}
          </>
        )}

        {tab === "season" && (
          <SeasonStatsPanel
            home={homeTeam?.season_stats ?? null}
            away={awayTeam?.season_stats ?? null}
            homeLabel={home}
            awayLabel={away}
          />
        )}

        {tab === "stats" && isFootball(prediction) && (
          <StatsComparison
            expectedGoalsHome={prediction.expected_goals_home}
            expectedGoalsAway={prediction.expected_goals_away}
            score={prediction.match_score}
            actual={prediction.actual_stats}
          />
        )}

        {tab === "form" && (
          <FormPanel
            home={homeTeam}
            away={awayTeam}
            homeLabel={home}
            awayLabel={away}
          />
        )}

        {tab === "h2h" && h2h && (
          <H2HPanel meetings={h2h.matches} home={home} away={away} />
        )}

        {tab === "recent" && (
          <RecentMatchesPanel
            home={home}
            away={away}
            homeMatches={homeTeam?.recent_matches ?? []}
            awayMatches={awayTeam?.recent_matches ?? []}
          />
        )}
      </div>
    </div>
  );
}
