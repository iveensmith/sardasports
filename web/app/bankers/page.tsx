/**
 * The day's likeliest picks.
 *
 * Selected on probability, not on the confidence score. Confidence is an
 * estimator-agreement measure and it does not discriminate: over 851 stored
 * predictions it runs 78.5 to 99.4 with a median of 94.4, so a threshold of
 * 8/10 admitted 29 of 29 fixtures on a real card. A filter that selects
 * everything is not a filter.
 *
 * The record travels with the list, and on a settled day it is the first
 * thing on the page. A page that offers a handful of near-certainties and
 * never mentions how the last batch went is asking to be believed on the
 * strength of its own adjectives.
 */

import { EngineError, getBankers, getSlip } from "@/lib/api";
import type { Bankers, Slip } from "@/lib/discover";
import { rate } from "@/lib/progress";
import { BoardTable } from "@/components/board/BoardTable";
import { SlipOfTheDay } from "@/components/slip/SlipOfTheDay";

export const revalidate = 300;

/** The price the automatic slip aims for. Modest on purpose: every extra leg
 * makes the whole thing less likely to land. */
const SLIP_OF_THE_DAY_TARGET = 4;

export const metadata = {
  title: "Bankers — UniquePredict",
  description:
    "The day's likeliest picks, with every settled one graded against the result.",
};

export default async function BankersPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const raw = params.date;
  const date = (Array.isArray(raw) ? raw[0] : raw) ?? "";

  let bankers: Bankers | null = null;
  let error: string | null = null;
  try {
    bankers = await getBankers(date || undefined);
  } catch (e) {
    error =
      e instanceof EngineError || e instanceof Error
        ? e.message
        : "The engine could not be reached.";
  }

  // A slip is only worth building for a card with matches still to play. It is
  // an extra on this page, so a failure to build one never takes the bankers
  // down with it.
  let slip: Slip | null = null;
  if (bankers && bankers.upcoming > 0) {
    slip = await getSlip({
      date: date || undefined,
      targetOdds: SLIP_OF_THE_DAY_TARGET,
      minLegs: 2,
      maxLegs: 4,
    }).catch(() => null);
  }

  if (error || !bankers) {
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

  const settled = bankers.record.settled > 0;
  const shown = new Date(bankers.date).toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 py-12">
      <header className="mb-6 max-w-[72ch]">
        <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
          {shown}
        </p>
        <h1 className="mt-2.5 text-[clamp(1.9rem,4.5vw,2.6rem)] leading-tight font-bold tracking-[-0.02em]">
          Bankers
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          {bankers.count === 1 ? "The one pick" : `The ${bankers.count} picks`}{" "}
          from this card&rsquo;s {bankers.considered} fixtures that the engine
          makes at least {bankers.min_probability.toFixed(0)}% likely, likeliest
          first. These are the safest calls on the card, which is not the same
          as the most valuable &mdash; a short price on a near-certainty is
          usually priced about right.
        </p>
      </header>

      {settled && (
        <div
          className="mb-6 rounded-[var(--radius-lg)] border p-5"
          style={{ borderColor: "var(--color-line-strong)" }}
        >
          <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
            How this batch went
          </p>
          <p className="mt-1.5 flex flex-wrap items-baseline gap-x-3">
            <span
              className="text-[28px] leading-none font-bold tabular-nums"
              style={{
                color:
                  (bankers.record.win_rate ?? 0) >= 50
                    ? "var(--color-won)"
                    : "var(--color-lost)",
              }}
            >
              {rate(bankers.record)}
            </span>
            <span className="text-[13.5px] text-[var(--color-text-dim)]">
              {bankers.record.won} won, {bankers.record.lost} lost
              {bankers.record.void > 0 && `, ${bankers.record.void} void`}
            </span>
          </p>
        </div>
      )}

      {bankers.count === 0 ? (
        <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-8">
          <p className="text-[15px] font-medium">
            Nothing on this card clears {bankers.min_probability.toFixed(0)}%
          </p>
          <p className="mt-2 max-w-[54ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
            That is a result, not a gap. Some days have no near-certainties on
            them, and padding the page out with 70% calls would misname them.
          </p>
        </div>
      ) : (
        <BoardTable rows={bankers.rows} />
      )}

      {slip && <SlipOfTheDay slip={slip} />}
    </div>
  );
}
