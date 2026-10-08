/**
 * Loads one sport's data and renders its page, or says plainly that it could not.
 *
 * Shared by `/basketball` and `/tennis` so the two cannot drift apart. A failed or
 * slow engine produces an explanation, not a blank page and not a thrown error.
 */

import { SportPage } from "@/components/sport/SportPage";
import { getSportBoard, getSportOverview, getSportRecord } from "@/lib/api";
import { SPORT_COPY } from "@/lib/sportContent";
import type {
  OtherSportKey,
  SportBoard,
  SportOverview,
  SportRecord,
} from "@/lib/sports";

export async function SportRoute({
  sport,
  date,
}: {
  sport: OtherSportKey;
  /** The day to show (YYYY-MM-DD); today when absent. */
  date?: string | null;
}) {
  const today = new Date().toISOString().slice(0, 10);
  // Each part stands on its own request: a slow board must not hide the models table.
  const [overview, board, record] = await Promise.all([
    getSportOverview(sport).catch(() => null),
    getSportBoard(sport, date ?? undefined).catch(() => null),
    getSportRecord(sport).catch(() => null),
  ]);
  const data: SportOverview | null = overview;
  const boardData: SportBoard | null = board;
  const recordData: SportRecord | null = record;

  if (!data) {
    const copy = SPORT_COPY[sport];
    return (
      <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
        <h1 className="text-[clamp(1.9rem,4.5vw,2.75rem)] leading-tight font-bold tracking-[-0.02em]">
          {copy.h1}
        </h1>
        <div className="mt-8 max-w-[72ch] rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[15px] font-medium">
            The figures could not be loaded just now
          </p>
          <p className="mt-2 text-[14px] leading-relaxed text-[var(--color-text-dim)]">
            The prediction engine did not answer in time. Nothing has been
            guessed in its place; try again in a minute.
          </p>
        </div>
      </div>
    );
  }

  return (
    <SportPage
      sport={sport}
      data={data}
      board={boardData}
      record={recordData}
      today={today}
    />
  );
}
