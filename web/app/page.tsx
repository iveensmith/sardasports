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
  getBoardDates,
  getDayBoard,
  getLeagues,
  getProgress,
} from "@/lib/api";
import { allRows, type DayBoard } from "@/lib/board";
import type { Progress } from "@/lib/progress";
import { rate } from "@/lib/progress";
import { BoardTable } from "@/components/board/BoardTable";
import { Hero } from "@/components/home/Hero";
import { ResultsTicker } from "@/components/home/ResultsTicker";
import { AboutTheEngine } from "@/components/home/AboutTheEngine";
import { HowItWorks } from "@/components/home/HowItWorks";
import { Faq } from "@/components/home/Faq";

export const revalidate = 180;

export const metadata = {
  title: "UniquePredict — football predictions, every one graded",
  description:
    "A calibrated prediction engine. Every pick is settled against the final score and the record is public, including what it got wrong.",
};

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
      <section id={id} className="mt-14 scroll-mt-20">
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
    <section id={id} className="mt-14 scroll-mt-20">
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

export default async function HomePage() {
  let yesterday: DayBoard | null = null;
  let today: DayBoard | null = null;
  let tomorrow: DayBoard | null = null;
  let progress: Progress | null = null;
  let settledDay: DayBoard | null = null;
  let error: string | null = null;
  let competitionCount: number | null = null;
  let countryCount: number | null = null;

  try {
    const [boards, dates, leagues] = await Promise.all([
      Promise.all([
        getDayBoard({ date: isoDay(-1) }).catch(() => null),
        getDayBoard({}),
        getDayBoard({ date: isoDay(1) }).catch(() => null),
        getProgress().catch(() => null),
      ]),
      getBoardDates(3).catch(() => null),
      getLeagues().catch(() => null),
    ]);
    [yesterday, today, tomorrow, progress] = boards;
    competitionCount = leagues?.competition_count ?? null;
    countryCount = leagues?.country_count ?? null;

    // The strip wants graded picks. Yesterday usually has none yet, so fall
    // back to the last day that actually settled rather than showing nothing.
    const settledDate = dates?.last_settled ?? null;
    settledDay =
      yesterday && yesterday.counts.finished > 0
        ? yesterday
        : settledDate
          ? await getDayBoard({ date: settledDate }).catch(() => null)
          : null;
  } catch (e) {
    error =
      e instanceof EngineError || e instanceof Error
        ? e.message
        : "The engine could not be reached.";
  }

  const hasLive = (progress?.live.record.settled ?? 0) > 0;
  const headline = hasLive ? progress!.live.record : progress?.overall;
  const winRate = headline && headline.settled > 0 ? rate(headline) : null;
  const isBacktest = !hasLive;

  const tickerRows = settledDay ? allRows(settledDay) : [];
  const tickerDate = settledDay?.date ?? null;

  return (
    <>
      <Hero
        winRate={winRate}
        settled={headline?.settled ?? 0}
        isBacktest={isBacktest}
        fixturesToday={today?.counts.fixtures ?? 0}
      />

      <ResultsTicker rows={tickerRows} date={tickerDate} />

      <div className="mx-auto w-full max-w-[1200px] px-4 pb-16 sm:px-6 lg:px-10">
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
          blurb="Every pick graded against the final result. This is the board that decides whether the two below are worth reading."
          unsettledBlurb="Results for these fixtures have not been ingested yet, so nothing here is graded. Once they are, every pick on this board settles automatically."
          emptyBlurb="No fixtures were ingested for yesterday's date."
          board={yesterday}
          href={`/matches?date=${isoDay(-1)}`}
        />

        <BoardSection
          id="today"
          title="Today"
          blurb="A pick in each market for every fixture the engine has a trained model for."
          emptyBlurb="Nothing has been ingested for today yet. Fixtures, odds and results are pulled in on a schedule rather than continuously, so an empty board here means the next ingest run hasn't happened — not that there is nothing to predict."
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

        <AboutTheEngine
          settled={headline?.settled ?? 0}
          winRate={winRate}
          isBacktest={isBacktest}
          competitionCount={competitionCount}
          countryCount={countryCount}
          firstSettledDate={progress?.span?.first ?? null}
        />

        <HowItWorks />

        <Faq
          winRate={winRate}
          settled={headline?.settled ?? 0}
          competitionCount={competitionCount}
          countryCount={countryCount}
        />
      </div>
    </>
  );
}
