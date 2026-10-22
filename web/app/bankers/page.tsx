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
import { BankersView } from "@/components/premium/BankersView";
import { pageMetadata } from "@/lib/seo";

export const revalidate = 300;

/** The price the automatic slip aims for. Modest on purpose: every extra leg
 * makes the whole thing less likely to land. */
const SLIP_OF_THE_DAY_TARGET = 4;

export const metadata = pageMetadata({
  title: "Football Banker Tips Today: Picks Rated 80%+",
  description:
    "The day's safest football picks, the ones our engine rates 80% likely or better, with how every settled batch went. Banker tips, graded in public.",
  path: "/bankers",
});

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
          Football banker tips
        </h1>
      </header>

      <BankersView
        initial={bankers}
        initialSlip={slip}
        date={date}
        slipTarget={SLIP_OF_THE_DAY_TARGET}
      />
    </div>
  );
}
