/**
 * The fixture's prediction, and the working behind it.
 *
 * `HeadlineCall` is the prediction: one selection, the likeliest thing to
 * happen across every market the engine prices. It is what the board row
 * shows and what this page leads with, read from the same field so the two
 * can never disagree.
 *
 * `MarketCallTable` is the working, and belongs only on the detail page. A
 * board row that listed several markets answered the question several times
 * over; a page someone has clicked into to read the analysis is exactly where
 * the alternatives belong.
 *
 * Both carry each call's base rate. "Over 1.5 goals, 76%" reads like a
 * finding until you know over 1.5 lands in 74.8% of all matches, at which
 * point it is a description of football rather than of this fixture. The base
 * rate never changes which prediction is made — probability alone decides
 * that — it tells a reader whether the number is about the fixture at all.
 */

import type { Call, Value } from "@/lib/types";

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
                  color: call.notable
                    ? "var(--color-text)"
                    : "var(--color-text-dim)",
                }}
              >
                {call.label}
              </td>
              <td className="py-2 text-right font-semibold">
                {call.probability.toFixed(1)}%
              </td>
              <td className="py-2 text-right text-[var(--color-text-faint)]">
                {call.base_rate === null
                  ? "—"
                  : `${call.base_rate.toFixed(1)}%`}
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

/**
 * The fixture's one prediction, stated once and prominently.
 *
 * Identical to the call on the board row, read from the same field, because
 * a row and its own detail page disagreeing is the bug this whole area has
 * now produced three times.
 *
 * The base rate sits underneath rather than beside it. It is not a second
 * prediction and must not read as one — it is the answer to "is this number
 * telling me about the fixture, or about football?"
 */
export function HeadlineCall({ call }: { call: Call }) {
  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
      <p className="text-[12px] tracking-wider text-[var(--color-text-faint)] uppercase">
        Prediction
      </p>
      <p className="mt-2 flex flex-wrap items-baseline gap-x-3">
        <span className="text-[clamp(1.35rem,3vw,1.9rem)] leading-tight font-bold tracking-[-0.02em]">
          {call.label}
        </span>
        <span
          className="text-[clamp(1.35rem,3vw,1.9rem)] leading-tight font-bold"
          style={{ color: "var(--color-gold-bright)" }}
        >
          {call.probability.toFixed(1)}%
        </span>
      </p>
      <p className="mt-2 max-w-[64ch] text-[13px] leading-relaxed text-[var(--color-text-dim)]">
        The likeliest outcome across every market the engine prices, in the{" "}
        {call.market_name.toLowerCase()} market.
        {call.base_rate !== null && (
          <>
            {" "}
            That selection lands {call.base_rate.toFixed(1)}% of the time across
            every completed match on record, so this fixture accounts for{" "}
            <span style={{ color: "var(--color-text)" }}>
              {call.lift !== null && call.lift >= 0 ? "+" : ""}
              {call.lift?.toFixed(1)} points
            </span>{" "}
            of it.
          </>
        )}
      </p>
    </section>
  );
}

/**
 * The market comparison, on the fixture page.
 *
 * This is the content that used to sit under every board row, where it
 * competed with the prediction and — worse — put a "+1344% expected value"
 * in larger type than anything else on the card. It is analysis, so it lives
 * where analysis is read.
 *
 * The unflattering case is stated plainly. Most selections against efficient
 * odds price worse than the model thinks they are worth; a page that only
 * narrated wins would be lying by omission. And where a competitor's rating
 * rests on too few matches, the warning comes before the number rather than
 * as a footnote to it.
 */
export function ValuePanel({ value }: { value: Value }) {
  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 className="text-[15px] font-semibold">Against the market</h2>
        {value.thin_evidence && (
          <span
            className="rounded border px-1.5 py-0.5 text-[10px] tracking-wide uppercase"
            style={{
              borderColor: "var(--color-away)",
              color: "var(--color-away)",
            }}
          >
            thin data
          </span>
        )}
      </div>

      <p className="mt-3 flex flex-wrap items-baseline gap-x-2 text-[15px]">
        <span className="text-[var(--color-text-dim)]">
          Best-priced selection:
        </span>
        <span className="font-semibold">{value.label}</span>
        <span className="text-[var(--color-text-dim)]">at</span>
        <span className="font-semibold">{value.offered_price.toFixed(2)}</span>
      </p>

      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 text-[13px] sm:grid-cols-4">
        {[
          ["Model", `${value.model_probability.toFixed(1)}%`],
          ["Market implies", `${value.market_implied_probability.toFixed(1)}%`],
          ["Fair price", value.fair_price.toFixed(2)],
          [
            "Expected value",
            `${value.expected_value >= 0 ? "+" : ""}${value.expected_value.toFixed(1)}%`,
          ],
        ].map(([label, figure]) => (
          <div key={label}>
            <dt className="text-[var(--color-text-faint)]">{label}</dt>
            <dd
              className="mt-0.5 text-[15px] font-semibold"
              style={{
                color:
                  label === "Expected value" && !value.thin_evidence
                    ? value.positive_value
                      ? "var(--color-gold-bright)"
                      : "var(--color-text-dim)"
                    : "var(--color-text)",
              }}
            >
              {figure}
            </dd>
          </div>
        ))}
      </dl>

      <p className="mt-4 max-w-[70ch] text-[13px] leading-relaxed text-[var(--color-text-dim)]">
        {value.rationale}
      </p>

      <p className="mt-3 max-w-[70ch] text-[12px] leading-relaxed text-[var(--color-text-faint)]">
        This is the price, not the prediction. The best-priced selection is
        frequently the least likely outcome on the fixture, and the
        engine&rsquo;s own backtest returns &minus;6.74% against bookmaker odds
        &mdash; so a large positive figure here is a reason to look harder, not
        a reason to bet.
      </p>
    </section>
  );
}
