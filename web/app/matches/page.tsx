/**
 * The browsable board: any day's fixtures, grouped by competition.
 *
 * Three things a reader needs and a card list cannot give them. A date strip,
 * because yesterday — where every pick is already settled — is the page that
 * decides whether today's is worth reading. A country filter, because a
 * hundred-fixture Saturday is unusable otherwise. And a table, because
 * picks in four markets across a hundred fixtures is a grid, and pretending
 * otherwise costs the reader the comparison that makes it useful.
 *
 * Everything is URL-driven: a day, a country, a competition are all links, so
 * any view is shareable and none of it needs client JavaScript.
 *
 * Next 16: `searchParams` is a Promise and must be awaited.
 */

import { EngineError, getBoardDates, getDayBoard } from "@/lib/api";
import type { BoardDates, DayBoard } from "@/lib/board";
import { BoardTable } from "@/components/board/BoardTable";
import { CountrySidebar } from "@/components/board/CountrySidebar";
import { DateStrip } from "@/components/board/DateStrip";
import { StatTiles } from "@/components/board/StatTiles";
import { MarketGlossary } from "@/components/MarketGlossary";
import { pageMetadata } from "@/lib/seo";

export const revalidate = 120;

/** A real YYYY-MM-DD, or null. Anything else in the URL is ignored, not echoed. */
function validDate(value: string | string[] | undefined): string | null {
  const first = Array.isArray(value) ? value[0] : value;
  return first && /^\d{4}-\d{2}-\d{2}$/.test(first) ? first : null;
}

export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const date = validDate((await searchParams).date);
  if (!date) {
    return pageMetadata({
      title: "Today's Football Predictions & Betting Tips",
      description:
        "Today's football predictions for every fixture the engine prices: 1X2, over/under goals and both teams to score, with every past pick graded against the result.",
      path: "/matches",
    });
  }
  const label = new Date(date).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
  // The country filter is the same card re-sliced, so it is not a separate
  // address: both resolve to the day's own page.
  return pageMetadata({
    title: `Football Predictions for ${label}`,
    description: `Football predictions and betting tips for ${label}: a pick in each market for every fixture the engine prices, graded against the result once played.`,
    path: `/matches?date=${date}`,
  });
}

function Empty({ date }: { date: string }) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-8">
      <p className="text-[15px] font-medium">No fixtures on {date}</p>
      <p className="mt-2 max-w-[54ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
        Either nothing is scheduled, or this day has not been ingested yet. Run{" "}
        <code className="text-[var(--color-text)]">
          scripts/fetch_upcoming_fixtures.py
        </code>{" "}
        to pull the next few days.
      </p>
    </div>
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

  const date = first("date");
  const country = first("country");
  const competition = first("competition");

  let board: DayBoard | null = null;
  let dates: BoardDates | null = null;
  let error: string | null = null;

  try {
    [board, dates] = await Promise.all([
      getDayBoard({
        date: date || undefined,
        country: country || undefined,
        competition: competition || undefined,
      }),
      getBoardDates(3),
    ]);
  } catch (e) {
    error =
      e instanceof EngineError
        ? e.message
        : e instanceof Error
          ? e.message
          : "The engine could not be reached.";
  }

  if (error || !board || !dates) {
    return (
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 py-12">
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[15px] font-medium">The engine is unreachable</p>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">
            {error}
          </p>
        </div>
      </div>
    );
  }

  const shown = new Date(board.date).toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  const settled = board.counts.finished > 0;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 py-10">
      <DateStrip days={dates.days} active={board.date} />

      <header className="mt-8 mb-5">
        <h1 className="text-[clamp(1.6rem,3.5vw,2.1rem)] font-bold tracking-[-0.02em]">
          Football predictions for {shown}
        </h1>
        <p className="mt-2 max-w-[70ch] text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
          {settled
            ? "Every pick on this card has been graded against the final result: won, lost, or void where the match records no such stat."
            : "A pick in each market for every fixture the engine has a trained model for. Each one is graded against the result once the match is played."}
        </p>
      </header>

      <StatTiles counts={board.counts} />

      <div className="mt-6 grid gap-6 lg:grid-cols-[210px_1fr]">
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <CountrySidebar
            countries={board.countries}
            active={country || null}
            date={board.date}
          />
        </aside>

        <main className="min-w-0">
          {board.groups.length === 0 ? (
            <Empty date={shown} />
          ) : (
            <div className="flex flex-col gap-7">
              {board.groups.map((group) => (
                <section key={group.competition.name}>
                  <div className="mb-2 flex flex-wrap items-baseline gap-x-2.5">
                    <h2 className="text-[15px] font-semibold">
                      {group.competition.short_name}
                    </h2>
                    {group.competition.country && (
                      <span className="text-[12.5px] text-[var(--color-text-faint)]">
                        {group.competition.country}
                      </span>
                    )}
                    <span className="ml-auto text-[12px] text-[var(--color-text-faint)]">
                      {group.rows.length} fixture
                      {group.rows.length === 1 ? "" : "s"}
                    </span>
                  </div>
                  <BoardTable rows={group.rows} />
                </section>
              ))}
            </div>
          )}
        </main>
      </div>

      <MarketGlossary />
    </div>
  );
}
