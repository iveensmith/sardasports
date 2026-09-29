/**
 * One Over/Under market, one row per line.
 *
 * The important behaviour here is the *third* state. A line has three
 * possible readings, not two:
 *
 *   1. priced by model + baseline  -> a real number, "Model"
 *   2. priced by the baseline only -> a real number, "Baseline"
 *   3. not priced at all           -> "N/A", and an em dash for the source
 *
 * Case 3 is genuine unavailability: the competition has no data for the
 * stat, so there was no model *and* no statistical fallback. Rendering it
 * as 0%, or labelling it "Baseline" off a bare `!model_used`, would claim a
 * calculation that never ran. The engine had this exact bug on its own API
 * once; it is not being reintroduced in the UI.
 */

import type { MarketLine } from "@/lib/types";

interface Props {
  title: string;
  markets: MarketLine[];
  /** Shown when every line is unavailable, to say why. */
  unavailableNote?: string;
}

export function MarketTable({ title, markets, unavailableNote }: Props) {
  const allUnavailable = markets.every((m) => m.prob_over === null);

  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
      <h3 className="mb-4 text-[15px] font-semibold">{title}</h3>

      <table className="w-full text-[14px]">
        <thead>
          <tr className="text-left text-[12px] text-[var(--color-text-faint)]">
            <th className="pb-2 font-medium">Line</th>
            <th className="pb-2 text-right font-medium">Over</th>
            <th className="pb-2 text-right font-medium">Under</th>
            <th className="pb-2 text-right font-medium">Source</th>
          </tr>
        </thead>
        <tbody>
          {markets.map((m) => {
            const unavailable = m.prob_over === null;
            return (
              <tr
                key={m.line}
                className="border-t border-[var(--color-line)]/60"
              >
                <td className="py-2.5">{m.line}</td>
                <td
                  className="py-2.5 text-right"
                  style={
                    unavailable ? { color: "var(--color-unknown)" } : undefined
                  }
                >
                  {unavailable ? "N/A" : `${m.prob_over!.toFixed(1)}%`}
                </td>
                <td
                  className="py-2.5 text-right"
                  style={
                    unavailable ? { color: "var(--color-unknown)" } : undefined
                  }
                >
                  {unavailable ? "N/A" : `${m.prob_under!.toFixed(1)}%`}
                </td>
                <td className="py-2.5 text-right text-[var(--color-text-faint)]">
                  {unavailable ? "—" : m.model_used ? "Model" : "Baseline"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {allUnavailable && unavailableNote && (
        <p className="mt-3 text-[13px] leading-relaxed text-[var(--color-text-faint)]">
          {unavailableNote}
        </p>
      )}
    </section>
  );
}
