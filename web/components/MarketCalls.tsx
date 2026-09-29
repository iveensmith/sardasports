/**
 * What the engine calls across every market it can price.
 *
 * The board used to answer one question — who wins — and drop everything
 * else the engine already computes. This shows the rest: double chance,
 * goals lines, both teams to score, half-time goals, corners and cards.
 *
 * Each call carries two numbers, and the second is the one that matters.
 * "Over 1.5 goals, 76%" reads like a finding until you know over 1.5 lands
 * in 74.8% of all matches, at which point it is a description of football
 * rather than of this fixture. So every call is shown against its own base
 * rate, and the lift between them is what gets the emphasis. A call whose
 * lift clears the notable threshold is marked; one that does not is still
 * shown, quietly, because "nothing unusual here" is a real answer.
 */

import type { Call } from "@/lib/types";

/** Compact strip for a board row: the few calls worth a glance. */
export function MarketCallStrip({ calls, max = 4 }: { calls: Call[]; max?: number }) {
  const shown = calls.slice(0, max);
  if (shown.length === 0) return null;

  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px]">
      {shown.map((call) => (
        <span
          key={`${call.market}:${call.selection}`}
          className="inline-flex items-baseline gap-1 rounded border px-1.5 py-0.5"
          style={{
            borderColor: call.notable
              ? "var(--color-gold-dim)"
              : "var(--color-line-strong)",
          }}
        >
          <span
            style={{
              color: call.notable ? "var(--color-text)" : "var(--color-text-dim)",
            }}
          >
            {call.label}
          </span>
          <span
            className="font-semibold"
            style={{
              color: call.notable ? "var(--color-gold-bright)" : "var(--color-text-dim)",
            }}
          >
            {call.probability.toFixed(0)}%
          </span>
          {call.lift !== null && (
            <span className="text-[11px] text-[var(--color-text-faint)]">
              {call.lift >= 0 ? "+" : ""}
              {call.lift.toFixed(0)}
            </span>
          )}
        </span>
      ))}
    </div>
  );
}

/** Full table for a fixture's detail page. */
export function MarketCallTable({ calls }: { calls: Call[] }) {
  if (calls.length === 0) return null;

  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
      <h2 className="text-[15px] font-semibold">Calls by market</h2>
      <p className="mt-1.5 max-w-[68ch] text-[13px] leading-relaxed text-[var(--color-text-dim)]">
        The engine&rsquo;s strongest selection in each market it can price.
        &ldquo;Base&rdquo; is how often that selection actually lands across
        every completed match on record, so the lift beside it &mdash; not the
        probability &mdash; is what this fixture adds. Over 1.5 goals lands in
        three matches out of four on its own.
      </p>

      <table className="mt-4 w-full text-[13px]">
        <thead>
          <tr className="text-left text-[12px] text-[var(--color-text-faint)]">
            <th className="pb-2 font-normal">Market</th>
            <th className="pb-2 font-normal">Call</th>
            <th className="pb-2 text-right font-normal">Model</th>
            <th className="pb-2 text-right font-normal">Base</th>
            <th className="pb-2 text-right font-normal">Lift</th>
          </tr>
        </thead>
        <tbody>
          {calls.map((call) => (
            <tr
              key={`${call.market}:${call.selection}`}
              className="border-t border-[var(--color-line)]"
            >
              <td className="py-2 text-[var(--color-text-faint)]">
                {call.market_name}
              </td>
              <td
                className="py-2"
                style={{
                  color: call.notable ? "var(--color-text)" : "var(--color-text-dim)",
                }}
              >
                {call.label}
              </td>
              <td className="py-2 text-right font-semibold">
                {call.probability.toFixed(1)}%
              </td>
              <td className="py-2 text-right text-[var(--color-text-faint)]">
                {call.base_rate === null ? "—" : `${call.base_rate.toFixed(1)}%`}
              </td>
              <td
                className="py-2 text-right font-semibold"
                style={{
                  color: call.notable
                    ? "var(--color-gold-bright)"
                    : "var(--color-text-faint)",
                }}
              >
                {call.lift === null
                  ? "—"
                  : `${call.lift >= 0 ? "+" : ""}${call.lift.toFixed(1)}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="mt-3 text-[12px] text-[var(--color-text-faint)]">
        A dash means the market has too little history on record to judge the
        call against, which is not the same as a lift of zero.
      </p>
    </section>
  );
}
