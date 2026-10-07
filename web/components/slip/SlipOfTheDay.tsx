/**
 * The day's accumulator, built automatically from the card.
 *
 * Shown beside the bankers because the reference site pairs "Bet of the Day"
 * with "Slip of the Day". The combined chance sits next to the combined price
 * on purpose and is not optional: several short-priced legs multiply into a bet
 * that usually loses, and a price shown alone would be advertising the half of
 * the sum that flatters it. The legs use bookmaker prices only — a slip built
 * on a price nobody offered could not be placed.
 */

import Link from "next/link";
import type { Slip } from "@/lib/discover";

export function SlipOfTheDay({ slip }: { slip: Slip }) {
  if (slip.leg_count === 0) return null;

  return (
    <section
      className="mt-10 rounded-[var(--radius-lg)] border bg-[var(--color-surface)] p-5"
      style={{ borderColor: "var(--color-line-strong)" }}
      aria-label="Slip of the day"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <h2 className="text-[15px] font-semibold">Slip of the day</h2>
        <p className="text-[13px] text-[var(--color-text-dim)]">
          {slip.leg_count} legs at{" "}
          <span className="font-semibold text-[var(--color-gold-bright)] tabular-nums">
            {slip.combined_odds.toFixed(2)}
          </span>
          <span className="mx-2 text-[var(--color-text-faint)]">·</span>
          chance every leg lands{" "}
          <span className="font-semibold text-[var(--color-text)] tabular-nums">
            {slip.combined_probability.toFixed(1)}%
          </span>
        </p>
      </div>

      <table className="mt-4 w-full text-[13px]">
        <thead>
          <tr className="text-left text-[11px] tracking-wider text-[var(--color-text-faint)] uppercase">
            <th className="pb-2 font-medium">Fixture</th>
            <th className="pb-2 font-medium">Selection</th>
            <th className="pb-2 text-right font-medium">Model</th>
            <th className="pb-2 text-right font-medium">Price</th>
          </tr>
        </thead>
        <tbody>
          {slip.legs.map((leg) => (
            <tr
              key={leg.match_id}
              className="border-t border-[var(--color-line)]"
            >
              <td className="py-2.5">
                <Link
                  href={`/match/${leg.slug}`}
                  className="hover:text-[var(--color-gold-bright)]"
                >
                  {leg.home_team} v {leg.away_team}
                </Link>
                <span className="block text-[11.5px] text-[var(--color-text-faint)]">
                  {leg.competition}
                </span>
              </td>
              <td className="py-2.5 text-[var(--color-text-dim)]">
                {leg.label}
              </td>
              <td className="py-2.5 text-right tabular-nums">
                {leg.probability.toFixed(1)}%
              </td>
              <td className="py-2.5 text-right font-semibold tabular-nums">
                {leg.odds.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="mt-4 max-w-[72ch] text-[12px] leading-relaxed text-[var(--color-text-faint)]">
        Every leg has to land. Each one added multiplies the price and divides
        the chance of a return. This is the engine&rsquo;s surest priced calls
        put together, not a recommendation to place a bet.{" "}
        <Link
          href="/slip"
          className="text-[var(--color-gold-bright)] hover:underline"
        >
          Build your own slip
        </Link>
        .
      </p>
    </section>
  );
}
