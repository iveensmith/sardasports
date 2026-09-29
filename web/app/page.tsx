/**
 * Home.
 *
 * Three boards, in the order that earns trust rather than the order that
 * flatters: yesterday first where every pick is already settled, then today,
 * then tomorrow. Most prediction sites run that sequence backwards and lead
 * with the unfalsifiable end of it.
 *
 * The hero carries the track record and labels it a backtest, because that is
 * what it currently is. When the live record has something in it this page
 * will lead with that instead, and it will be a stronger claim honestly made.
 */

import Link from "next/link";
import { EngineError, getDayBoard, getProgress } from "@/lib/api";
import { allRows, type DayBoard } from "@/lib/board";
import type { Progress } from "@/lib/progress";
import { rate } from "@/lib/progress";
import { BoardTable } from "@/components/board/BoardTable";

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
  title,
  settledTitle,
  blurb,
  unsettledBlurb,
  board,
  href,
}: {
  title: string;
  /** Used only once something on the board has actually been graded. */
  settledTitle?: string;
  blurb: string;
  unsettledBlurb?: string;
  board: DayBoard | null;
  href: string;
}) {
  const rows = board ? allRows(board) : [];
  if (rows.length === 0) return null;

  // Whether anything here has a result yet. A past day whose results have not
  // been ingested is not a settled board, and labelling it as one would be
  // claiming an accountability the page is not currently delivering.
  const settled = board!.counts.finished > 0;
  const heading = settled && settledTitle ? settledTitle : title;
  const copy = !settled && unsettledBlurb ? unsettledBlurb : blurb;

  return (
    <section className="mt-12">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div>
          <h2 className="text-[21px] font-bold tracking-[-0.018em]">
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
            All fixtures →
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
  let error: string | null = null;

  try {
    [yesterday, today, tomorrow, progress] = await Promise.all([
      getDayBoard({ date: isoDay(-1) }).catch(() => null),
      getDayBoard({}),
      getDayBoard({ date: isoDay(1) }).catch(() => null),
      getProgress().catch(() => null),
    ]);
  } catch (e) {
    error =
      e instanceof EngineError || e instanceof Error
        ? e.message
        : "The engine could not be reached.";
  }

  const hasLive = (progress?.live.record.settled ?? 0) > 0;
  const headline = hasLive ? progress!.live.record : progress?.overall;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 py-12">
      <header className="max-w-[70ch]">
        <h1 className="text-[clamp(2.1rem,5.5vw,3.25rem)] leading-[1.06] font-bold tracking-[-0.025em]">
          Every prediction,{" "}
          <span style={{ color: "var(--color-gold-bright)" }}>graded</span>.
        </h1>
        <p className="mt-4 text-[16px] leading-relaxed text-[var(--color-text-dim)]">
          A calibrated engine blends three independent estimators across seven
          markets. Every call it makes is settled against the final score, the
          record is published including what it got wrong, and a market it
          cannot price is shown as unavailable rather than guessed.
        </p>

        {headline && headline.settled > 0 && (
          <div className="mt-6 flex flex-wrap items-baseline gap-x-6 gap-y-2">
            <span className="flex items-baseline gap-2">
              <span
                className="text-[30px] leading-none font-bold tabular-nums"
                style={{ color: "var(--color-gold-bright)" }}
              >
                {rate(headline)}
              </span>
              <span className="text-[13.5px] text-[var(--color-text-dim)]">
                {hasLive ? "live" : "backtested"} over{" "}
                {headline.settled.toLocaleString()} settled calls
              </span>
            </span>
            <Link
              href="/progress"
              className="text-[13.5px] text-[var(--color-gold-bright)] underline-offset-4 hover:underline"
            >
              See the full record →
            </Link>
          </div>
        )}

        {!hasLive && (
          <p className="mt-3 max-w-[66ch] text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
            That figure is a backtest: the predictions behind it were generated
            after the matches were played, from history truncated at kick-off.
            It is labelled as such everywhere it appears, and the live record
            starts filling on its own as the board runs forward.
          </p>
        )}
      </header>

      {error && (
        <div className="mt-8 rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
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
        board={yesterday}
        href={`/matches?date=${isoDay(-1)}`}
      />

      <BoardSection
        title="Today"
        blurb="A pick in each market for every fixture the engine has a trained model for."
        board={today}
        href="/matches"
      />

      <BoardSection
        title="Tomorrow"
        blurb="Priced as soon as the fixtures and odds are ingested."
        board={tomorrow}
        href={`/matches?date=${isoDay(1)}`}
      />
    </div>
  );
}
