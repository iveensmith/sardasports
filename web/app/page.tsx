/**
 * Home.
 *
 * Follows the reference site's shape — full-bleed hero, a moving strip of
 * results, then the day's picks as tables — with two deliberate departures.
 *
 * The strip carries *settled* results rather than upcoming ones. A ticker of
 * things that have not happened yet is advertising; a ticker of graded ones
 * is this site's whole argument, scrolling.
 *
 * And the boards run yesterday, today, tomorrow. Most prediction sites run
 * that order backwards and open on the unfalsifiable end of it. Yesterday is
 * where every pick is already settled, so it is the board that decides
 * whether the two below it are worth reading, and it goes first.
 */

import Link from "next/link";
import {
  EngineError,
  getDayBoard,
  getLeagues,
  getLiveBoard,
  getProgress,
  getRecentSettled,
  getSportBoardQuick,
  getSportsSummary,
} from "@/lib/api";
import { allRows, type DayBoard } from "@/lib/board";
import type { RecentSettled } from "@/lib/api";
import type { LeagueCountry } from "@/lib/discover";
import type { Progress } from "@/lib/progress";
import { BoardTable } from "@/components/board/BoardTable";
import { HomeHero } from "@/components/home/HomeHero";
import { FeatureStrip } from "@/components/home/FeatureStrip";
import { FeaturedPredictions } from "@/components/home/FeaturedPredictions";
import { BrowseSports } from "@/components/home/BrowseSports";
import { RecordPanel } from "@/components/home/RecordPanel";
import { LatestResults } from "@/components/home/LatestResults";
import { LiveNow } from "@/components/home/LiveNow";
import { pickFeatured } from "@/lib/featured";
import { AboutTheEngine } from "@/components/home/AboutTheEngine";
import { HowItWorks } from "@/components/home/HowItWorks";
import { TopLeagues } from "@/components/home/TopLeagues";
import { Faq } from "@/components/home/Faq";
import { GoodSite } from "@/components/home/GoodSite";
import { pageMetadata } from "@/lib/seo";

export const revalidate = 180;

export const metadata = pageMetadata({
  title: "Best AI Prediction Site: Football, Basketball & Tennis",
  description:
    "SARDASPORTS, the best AI prediction site for football: free predictions for today's matches, graded in public. Plus basketball and tennis predictions.",
  path: "/",
  absoluteTitle: true,
});

function isoDay(offset: number): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + offset);
  return day.toISOString().slice(0, 10);
}

function BoardSection({
  id,
  title,
  settledTitle,
  blurb,
  unsettledBlurb,
  emptyBlurb,
  board,
  href,
}: {
  id?: string;
  title: string;
  /** Used only once something on the board has actually been graded. */
  settledTitle?: string;
  blurb: string;
  unsettledBlurb?: string;
  /** Shown when the day genuinely has no fixtures at all. */
  emptyBlurb?: string;
  board: DayBoard | null;
  href: string;
}) {
  const rows = board ? allRows(board) : [];

  // A past day whose results have not been ingested is not a settled board,
  // and labelling it as one would claim an accountability this page is not
  // currently delivering.
  const settled = (board?.counts.finished ?? 0) > 0;
  const heading = settled && settledTitle ? settledTitle : title;

  // An empty day is a real, expected state right now — fixtures are ingested
  // a few days ahead of odds and results, so "today" can legitimately have
  // nothing yet. /matches says so outright when you land on such a day; the
  // home page used to just drop the section with no heading and no
  // explanation, which read as the site being broken rather than a gap in
  // what has been ingested so far.
  if (rows.length === 0) {
    return (
      <section id={id} className="scroll-mt-20">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 className="text-[22px] font-bold tracking-[-0.022em]">{title}</h2>
          <Link
            href={href}
            className="text-[13px] text-[var(--color-gold-bright)] underline-offset-4 hover:underline"
          >
            All fixtures
          </Link>
        </div>
        <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
            {emptyBlurb ??
              "Either nothing is scheduled, or this day has not been ingested yet."}
          </p>
        </div>
      </section>
    );
  }

  const copy = !settled && unsettledBlurb ? unsettledBlurb : blurb;

  return (
    <section id={id} className="scroll-mt-20">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div>
          <h2 className="text-[22px] font-bold tracking-[-0.022em]">
            {heading}
          </h2>
          <p className="mt-1 max-w-[68ch] text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
            {copy}
          </p>
        </div>
        <div className="flex items-baseline gap-4">
          {settled && (
            <span className="text-[13px]">
              <span
                className="font-semibold tabular-nums"
                style={{ color: "var(--color-won)" }}
              >
                {board!.counts.won}/{board!.counts.finished}
              </span>{" "}
              <span className="text-[var(--color-text-faint)]">
                best tips won
              </span>
            </span>
          )}
          <Link
            href={href}
            className="text-[13px] text-[var(--color-gold-bright)] underline-offset-4 hover:underline"
          >
            All fixtures
          </Link>
        </div>
      </div>
      <BoardTable rows={rows.slice(0, 10)} />
      {rows.length > 10 && (
        <p className="mt-2 text-[12.5px] text-[var(--color-text-faint)]">
          Showing 10 of {rows.length}.{" "}
          <Link href={href} className="underline underline-offset-4">
            See the rest
          </Link>
          .
        </p>
      )}
    </section>
  );
}

/** A value and, if it failed, why: lets one failing request be reported without throwing. */
async function settle<T>(
  work: Promise<T>,
): Promise<{ value: T | null; error: string | null }> {
  try {
    return { value: await work, error: null };
  } catch (e) {
    return {
      value: null,
      error:
        e instanceof EngineError || e instanceof Error
          ? e.message
          : "The engine could not be reached.",
    };
  }
}

export default async function HomePage() {
  let yesterday: DayBoard | null = null;
  let today: DayBoard | null = null;
  let tomorrow: DayBoard | null = null;
  let progress: Progress | null = null;
  let recent: RecentSettled | null = null;
  let error: string | null = null;
  let competitionCount: number | null = null;
  let countryCount: number | null = null;
  let leagueCountries: LeagueCountry[] | null = null;

  // The results strip is fetched on its own and cannot fail: if today's board,
  // the leagues or the record is slow or down, none of that may take the strip
  // with it. (It used to share one Promise.all with today's board, so one failed
  // request threw the strip away even when its own request had succeeded.)
  const recentPromise = getRecentSettled(24);

  // Each section stands on its own request, so one failing leaves the others up.
  // Only today's board is worth an error banner: it is the page's main content.
  const [
    yesterdayBoard,
    todayResult,
    tomorrowBoard,
    record,
    leaguesData,
    sportsData,
    basketballToday,
    basketballTomorrow,
    tennisToday,
    tennisTomorrow,
    liveBoard,
  ] = await Promise.all([
    getDayBoard({ date: isoDay(-1) }).catch(() => null),
    settle(getDayBoard({})),
    getDayBoard({ date: isoDay(1) }).catch(() => null),
    getProgress().catch(() => null),
    getLeagues().catch(() => null),
    getSportsSummary().catch(() => null),
    // The featured row's basketball and tennis picks. Each has its own short
    // timeout and a null on failure, so a slow board costs a card, not the page.
    getSportBoardQuick("basketball", isoDay(0)),
    getSportBoardQuick("basketball", isoDay(1)),
    getSportBoardQuick("tennis", isoDay(0)),
    getSportBoardQuick("tennis", isoDay(1)),
    getLiveBoard(),
  ]);
  yesterday = yesterdayBoard;
  today = todayResult.value;
  error = todayResult.error;
  tomorrow = tomorrowBoard;
  progress = record;
  competitionCount = leaguesData?.competition_count ?? null;
  countryCount = leaguesData?.country_count ?? null;
  leagueCountries = leaguesData?.countries ?? null;

  recent = await recentPromise;

  const hasLive = (progress?.live.record.settled ?? 0) > 0;
  const backtestRecord =
    (progress?.backtest.record.settled ?? 0) > 0
      ? progress!.backtest.record
      : null;

  const strongRecord = progress?.strong
    ? {
        record: progress.strong.record,
        minProbability: progress.strong.min_probability,
      }
    : null;

  const featured = pickFeatured({
    footballToday: today,
    footballTomorrow: tomorrow,
    basketball: [basketballToday, basketballTomorrow],
    tennis: [tennisToday, tennisTomorrow],
  });

  return (
    <>
      <HomeHero fixturesToday={today?.counts.fixtures ?? 0} />

      <FeatureStrip />

      {/* The landing sections, each a self-contained block with its own heading
          and spacing. Below them, the day's boards: the product itself. */}
      <div className="mx-auto w-full max-w-[1200px] space-y-14 px-4 pt-12 sm:px-6 lg:px-10">
        <LiveNow rows={liveBoard?.rows ?? []} />
        <FeaturedPredictions cards={featured} />
        <BrowseSports sports={sportsData?.sports ?? null} />
        <RecordPanel
          live={hasLive ? progress!.live.record : null}
          strong={strongRecord}
          backtest={backtestRecord}
        />
        <LatestResults
          rows={recent?.rows ?? []}
          minProbability={
            recent?.strong_only ? (recent.min_probability ?? 70) : null
          }
        />
      </div>

      {/* One rule for the page's rhythm: every section after the first is set
          off by a hairline and the same breathing room above and below it, so no
          section can drift out of step. The first sits under the results strip,
          which has its own rule. */}
      <div className="mx-auto w-full max-w-[1200px] px-4 pb-16 sm:px-6 lg:px-10 [&>section]:mt-12 [&>section+section]:border-t [&>section+section]:border-[var(--color-line)] [&>section+section]:pt-12">
        {error && (
          <div className="mt-10 rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
            <p className="text-[15px] font-medium">The engine is unreachable</p>
            <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">
              {error}
            </p>
          </div>
        )}

        <BoardSection
          title="Yesterday"
          settledTitle="Yesterday, settled"
          blurb="Every pick graded against the final result, so today's and tomorrow's boards can be judged against it."
          unsettledBlurb="Results for these fixtures have not been ingested yet, so nothing here is graded. Once they are, every pick on this board settles automatically."
          emptyBlurb="No fixtures were ingested for yesterday's date."
          board={yesterday}
          href={`/matches?date=${isoDay(-1)}`}
        />

        <BoardSection
          id="today"
          title="Today"
          blurb="A pick in each market for every fixture the engine has a trained model for."
          emptyBlurb="Nothing has been ingested for today yet. Fixtures, prices and results are pulled in on a schedule rather than continuously, so an empty board means the next ingest has not run, not that there is nothing to predict."
          board={today}
          href="/matches"
        />

        <BoardSection
          title="Tomorrow"
          blurb="Priced as soon as the fixtures and odds are ingested."
          emptyBlurb="Tomorrow's fixtures have not been ingested yet."
          board={tomorrow}
          href={`/matches?date=${isoDay(1)}`}
        />

        <TopLeagues countries={leagueCountries} />

        <AboutTheEngine
          gradedPicks={progress?.overall.settled ?? 0}
          livePicks={progress?.live.record.settled ?? 0}
          competitionCount={competitionCount}
          countryCount={countryCount}
          firstSettledDate={progress?.span?.first ?? null}
        />

        <HowItWorks />

        <GoodSite />

        <Faq
          live={hasLive ? progress!.live.record : null}
          backtest={backtestRecord}
          competitionCount={competitionCount}
          countryCount={countryCount}
        />
      </div>
    </>
  );
}
