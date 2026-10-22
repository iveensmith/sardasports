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
  competitors,
  isBasketball,
  isFootball,
  isLocked,
  isTennis,
  type FootballPrediction,
  type LockedPrediction,
  type Prediction,
} from "@/lib/types";
import { MarketTable } from "@/components/MarketTable";
import { ProbabilitySplit } from "@/components/ProbabilitySplit";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { FootballBody, Stat } from "@/components/match/FootballBody";
import { MemberMatchView } from "@/components/premium/MemberMatchView";
import { MatchHeader } from "@/components/match/MatchHeader";
import { GoalTimeline } from "@/components/match/GoalTimeline";
import { StatsComparison } from "@/components/match/StatsComparison";
import { SeasonStatsPanel } from "@/components/match/SeasonStatsPanel";
import { FormPanel } from "@/components/match/FormPanel";
import { H2HPanel } from "@/components/match/H2HPanel";
import { RecentMatchesPanel } from "@/components/match/RecentMatchesPanel";
import { MatchTabs, type MatchTab } from "@/components/match/MatchTabs";
import { JsonLd } from "@/components/seo/JsonLd";
import { ActiveSport } from "@/components/sport/ActiveSport";
import { SPORT_LABELS, SPORT_PATHS, monogramBadge } from "@/lib/sports";
import {
  breadcrumbLd,
  matchPath,
  pageMetadata,
  sportsEventLd,
} from "@/lib/seo";

export const revalidate = 60;

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
          Basketball plays overtime until someone wins. There were no ties in
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

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const matchId = matchIdFromSlug(id);
  const prediction =
    matchId === null ? null : await getPrediction(matchId).catch(() => null);
  if (matchId === null || !prediction) {
    return {
      title: "Match not found",
      robots: { index: false, follow: true },
    };
  }

  const { home, away } = competitors(prediction);
  const when = new Date(prediction.match_date).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
  const markets =
    isLocked(prediction) || isFootball(prediction)
      ? "win probabilities, goals and BTTS picks"
      : "win probabilities and totals";
  return pageMetadata({
    title: `${home} vs ${away} Prediction & Betting Tips`,
    description: `${home} vs ${away} prediction (${prediction.competition}, ${when}): ${markets}, form and head-to-head.`,
    // The readable address, whichever form the visitor arrived on.
    path: matchPath(home, away, matchId),
  });
}

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

  let prediction: Prediction | LockedPrediction;
  try {
    prediction = await getPrediction(matchId);
  } catch (error) {
    if (error instanceof EngineError && error.status === 404) notFound();
    throw error;
  }

  // A football match still to be played, outside the day's 15 free ones, arrives as who is playing
  // and when and nothing the engine worked out. `full` is the ordinary prediction, or null then.
  const locked = isLocked(prediction);
  const full: Prediction | null = isLocked(prediction) ? null : prediction;
  const football: FootballPrediction | LockedPrediction | null = isLocked(prediction)
    ? prediction
    : full !== null && isFootball(full)
      ? full
      : null;

  const { home, away } = competitors(prediction);
  // Badges are football-only for now — basketball and tennis carry no
  // `home_badge`/`away_badge` fields, so this degrades to no crest rather
  // than a type error or a fabricated flag.
  const homeBadge = football ? football.home_badge : monogramBadge(home);
  const awayBadge = football ? football.away_badge : monogramBadge(away);
  // Where "back" goes depends on the sport: a tennis match belongs to the tennis
  // page, not to the football board.
  const sectionPath = SPORT_PATHS[prediction.sport];
  const sectionLabel = SPORT_LABELS[prediction.sport];

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

  const tabs: MatchTab[] = football
    ? ["tips", "season", "stats", "form", "h2h", "recent"]
    : ["tips", "season", "form", "h2h", "recent"];

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 py-10">
      <JsonLd
        data={[
          breadcrumbLd([
            { name: "Home", path: "/" },
            {
              name: football ? "Matches" : `${sectionLabel} predictions`,
              path: sectionPath,
            },
            {
              name: `${home} vs ${away}`,
              path: matchPath(home, away, matchId),
            },
          ]),
          ...(football
            ? [
                sportsEventLd({
                  name: `${home} vs ${away}`,
                  path: matchPath(home, away, matchId),
                  startDate: football.match_date,
                  homeTeam: home,
                  awayTeam: away,
                  competition: football.competition,
                  played: football.match_status === "completed",
                }),
              ]
            : []),
        ]}
      />
      <ActiveSport sport={prediction.sport} />
      <Link
        href={sectionPath}
        className="text-[14px] text-[var(--color-text-dim)] underline-offset-4 hover:text-[var(--color-text)] hover:underline"
      >
        {football ? "Back to matches" : `Back to ${sectionLabel.toLowerCase()}`}
      </Link>

      <h1 className="mt-4 text-[clamp(1.4rem,3vw,1.9rem)] leading-tight font-bold tracking-[-0.02em]">
        {home} vs {away} prediction
      </h1>

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
          score={full ? full.match_score : null}
          live={full?.live ?? null}
          htScore={full && isFootball(full) ? full.ht_score : null}
          odds={prediction.odds_1x2}
          teamLinks={football !== null}
        />
      </div>

      {full && isFootball(full) && full.events.length > 0 && (
        <div className="mt-4">
          <GoalTimeline
            events={full.events}
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
            {locked && <MemberMatchView matchId={matchId} view="tips" />}
            {full && isFootball(full) && <FootballBody p={full} />}
            {full && isBasketball(full) && <BasketballBody p={full} />}
            {full && isTennis(full) && <TennisBody p={full} />}
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

        {tab === "stats" && locked && (
          <MemberMatchView matchId={matchId} view="stats" />
        )}
        {tab === "stats" && full && isFootball(full) && (
          <StatsComparison
            expectedGoalsHome={full.expected_goals_home}
            expectedGoalsAway={full.expected_goals_away}
            score={full.match_score}
            actual={full.actual_stats}
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
