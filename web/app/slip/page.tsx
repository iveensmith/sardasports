/**
 * The accumulator builder.
 *
 * This is the page on a prediction site most likely to mislead, so it is
 * built to say the uncomfortable number as loudly as the attractive one.
 *
 * An accumulator multiplies its legs' prices and needs every one of them to
 * land. Five legs the engine likes at around 73% each is a 5.11 price and a
 * 19% chance of any return at all. A builder that prints "5.11x" in large
 * type and leaves the 19% out is not simplifying — it has calculated the
 * downside and withheld it. So the combined probability is given the same
 * size and weight as the combined price, and the page says in words that
 * longer slips are worse bets, because the arithmetic says so and a reader
 * moving the target slider upward is walking away from it.
 *
 * The controls are links rather than a form, so every slip is a shareable
 * URL and the page needs no client JavaScript.
 *
 * Next 16: `searchParams` is a Promise and must be awaited.
 */

import Link from "next/link";
import { EngineError, getSlip } from "@/lib/api";
import type { Slip } from "@/lib/discover";
import { pageMetadata } from "@/lib/seo";

export const revalidate = 300;

export const metadata = pageMetadata({
  title: "Free Accumulator Builder for Football Bet Slips",
  description:
    "Build a football accumulator from today's priced picks: set a target price and legs, and see the combined price beside the chance every leg lands.",
  path: "/slip",
});

const TARGETS = [2, 3, 5, 10, 20];
const LEG_CAPS = [3, 4, 5, 6, 8];

function Controls({
  label,
  options,
  active,
  param,
  other,
  suffix = "",
}: {
  label: string;
  options: number[];
  active: number;
  param: string;
  other: Record<string, string>;
  suffix?: string;
}) {
  return (
    <div>
      <p className="mb-1.5 text-[11px] tracking-wider text-[var(--color-text-faint)] uppercase">
        {label}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => {
          const query = new URLSearchParams({
            ...other,
            [param]: String(option),
          });
          const isActive = option === active;
          return (
            <Link
              key={option}
              href={`/slip?${query}`}
              className="rounded-[var(--radius-md)] border px-3 py-1.5 text-[13px] transition-colors"
              style={
                isActive
                  ? {
                      borderColor: "var(--color-gold)",
                      color: "var(--color-gold-bright)",
                      fontWeight: 600,
                    }
                  : {
                      borderColor: "var(--color-line-strong)",
                      color: "var(--color-text-dim)",
                    }
              }
            >
              {option}
              {suffix}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export default async function SlipPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const first = (key: string) => {
    const value = params[key];
    return (Array.isArray(value) ? value[0] : value) ?? "";
  };

  const targetOdds = Number(first("target_odds")) || 5;
  const maxLegs = Number(first("max_legs")) || 6;

  let slip: Slip | null = null;
  let error: string | null = null;
  try {
    slip = await getSlip({
      targetOdds,
      maxLegs,
      minLegs: Math.min(3, maxLegs),
    });
  } catch (e) {
    error =
      e instanceof EngineError || e instanceof Error
        ? e.message
        : "The engine could not be reached.";
  }

  if (error || !slip) {
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

  const shared = {
    target_odds: String(targetOdds),
    max_legs: String(maxLegs),
  };
  // Rounded to whole pounds of stake-per-return, which is how a reader
  // actually reads a price: "about one in five".
  const oneIn =
    slip.combined_probability > 0
      ? Math.round(100 / slip.combined_probability)
      : null;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 py-12">
      <header className="mb-7 max-w-[72ch]">
        <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
          Built from today&rsquo;s card
        </p>
        <h1 className="mt-2.5 text-[clamp(1.9rem,4.5vw,2.6rem)] leading-tight font-bold tracking-[-0.02em]">
          Football accumulator builder
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          An accumulator from the engine&rsquo;s surest priced picks, one leg
          per fixture. Two selections from the same match tend to land together,
          so combining them would overstate the price.
        </p>
      </header>

      <div className="mb-7 flex flex-wrap gap-8 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
        <Controls
          label="Target price"
          options={TARGETS}
          active={targetOdds}
          param="target_odds"
          other={{ max_legs: shared.max_legs }}
          suffix="x"
        />
        <Controls
          label="Most legs"
          options={LEG_CAPS}
          active={maxLegs}
          param="max_legs"
          other={{ target_odds: shared.target_odds }}
        />
      </div>

      {/* Price and chance, same size. The whole point of the page. */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
            Combined price
          </p>
          <p
            className="mt-1.5 text-[40px] leading-none font-bold tabular-nums"
            style={{ color: "var(--color-gold-bright)" }}
          >
            {slip.combined_odds.toFixed(2)}x
          </p>
          <p className="mt-2 text-[12.5px] text-[var(--color-text-faint)]">
            {slip.leg_count} leg{slip.leg_count === 1 ? "" : "s"} from{" "}
            {slip.candidates_considered} eligible fixtures
          </p>
        </div>

        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
            Chance every leg lands
          </p>
          <p className="mt-1.5 text-[40px] leading-none font-bold tabular-nums">
            {slip.combined_probability.toFixed(1)}%
          </p>
          <p className="mt-2 text-[12.5px] text-[var(--color-text-faint)]">
            {oneIn ? `roughly one slip in ${oneIn}` : "no return expected"}
          </p>
        </div>
      </div>

      {!slip.reached_target && slip.leg_count > 0 && (
        <p className="mt-4 text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
          Today&rsquo;s card could not reach {targetOdds}x within {maxLegs} legs
          at these prices. The slip below is what it could do. Raising the leg
          cap gets closer to the target and lowers the chance of a return. That
          trade-off is what this page is for.
        </p>
      )}

      {slip.short_of_minimum && (
        <p className="mt-4 text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
          Not enough priced fixtures on this card to build a full slip. Odds are
          only ingested for the next few days, so older and further-out dates
          have fewer legs available.
        </p>
      )}

      {slip.leg_count === 0 ? (
        <div className="mt-6 rounded-[var(--radius-lg)] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-8">
          <p className="text-[15px] font-medium">No slip could be built</p>
          <p className="mt-2 max-w-[54ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
            Nothing on today&rsquo;s card has a bookmaker price inside the leg
            limits. Run{" "}
            <code className="text-[var(--color-text)]">
              scripts/fetch_odds.py
            </code>{" "}
            to pull prices.
          </p>
        </div>
      ) : (
        <section className="mt-6 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
          <h2 className="text-[15px] font-semibold">The slip</h2>
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
        </section>
      )}

      <p className="mt-7 max-w-[72ch] text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
        Every leg has to land. Each one added multiplies the price and divides
        the chance of a return, and against real bookmaker margins the second
        effect is the larger. The engine&rsquo;s last recorded backtest against
        bookmaker odds lost 6.74% on single picks, and an accumulator compounds
        that. This is a tool for building a slip, not a recommendation to place
        one.
      </p>
    </div>
  );
}
