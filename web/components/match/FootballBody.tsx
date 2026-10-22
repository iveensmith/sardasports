/**
 * The football prediction, as the match page's "Match tips" tab shows it: the headline call, the
 * outcome split, confidence, the estimators, every market and what drove it.
 *
 * Its own file so a premium member's browser can render the same thing for a match the public page
 * was sent without a prediction (see `components/premium/MemberMatchView.tsx`).
 */

import {
  HeadlineCall,
  MarketCallTable,
  ValuePanel,
} from "@/components/MarketCalls";
import { competitors, type FootballPrediction } from "@/lib/types";
import { ProbabilitySplit } from "@/components/ProbabilitySplit";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { MarketTable } from "@/components/MarketTable";
import { EstimatorBreakdown } from "@/components/EstimatorSplit";
import { agreementFrom } from "@/lib/agreement";

export function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[var(--color-surface)] px-4 py-3">
      <p className="text-[12px] text-[var(--color-text-faint)]">{label}</p>
      <p className="mt-1 text-[22px] leading-none font-semibold">{value}</p>
    </div>
  );
}

export function FootballBody({
  p,
}: {
  p: FootballPrediction;
}) {
  const { home, away } = competitors(p);
  return (
    <>
      {p.calls?.headline && <HeadlineCall call={p.calls.headline} />}

      <div className="mt-4 grid gap-4 md:grid-cols-[1.6fr_1fr]">
        <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
          <h2 className="mb-4 text-[15px] font-semibold">Outcome</h2>
          <ProbabilitySplit
            home={p.home_win}
            away={p.away_win}
            draw={p.draw}
            homeLabel={home}
            awayLabel={away}
          />
        </section>
        <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
          <ConfidenceMeter value={p.confidence} label={p.confidence_label} />
        </section>
      </div>

      <section className="mt-4 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
        <EstimatorBreakdown
          agreement={agreementFrom(p)}
          homeLabel={home}
          awayLabel={away}
        />
      </section>

      {/* The tables that follow are the working; the headline call above is
          the conclusion. */}
      {p.calls && p.calls.by_market.length > 0 && (
        <div className="mt-4">
          <MarketCallTable calls={p.calls.by_market} />
        </div>
      )}

      {/* The market comparison, moved off the board row. A different subject
          from the prediction, and one that needs room to be honest about
          what a large expected value usually means. */}
      {p.value && (
        <div className="mt-4">
          <ValuePanel value={p.value} />
        </div>
      )}

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Expected goals (home)" value={p.expected_goals_home} />
        <Stat label="Expected goals (away)" value={p.expected_goals_away} />
        <Stat label="Both teams score" value={`${p.btts_yes}%`} />
        <Stat
          label="Most likely score"
          value={p.top_scorelines[0]?.score ?? "—"}
        />
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <MarketTable
          title="Goals"
          markets={p.goals_markets}
          unavailableNote="This competition has no goal data the engine can price."
        />
        <MarketTable
          title="Half-time goals"
          markets={p.ht_goals_markets}
          unavailableNote="Half-time scores are not recorded for this competition."
        />
        <MarketTable
          title="Corners"
          markets={p.corners_markets}
          unavailableNote="This competition has no corner data, so these lines cannot be priced."
        />
        <MarketTable
          title="Cards"
          markets={p.cards_markets}
          unavailableNote="This competition has no card data, so these lines cannot be priced."
        />
      </div>

      {p.explanation && p.explanation.length > 0 && (
        <section className="mt-4 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
          <h3 className="text-[15px] font-semibold">What drove this</h3>
          <p className="mt-1 mb-4 text-[13px] text-[var(--color-text-dim)]">
            The features that moved the predicted outcome most, from the model
            itself rather than a written-after-the-fact rationale.
          </p>
          <ul className="space-y-2.5">
            {p.explanation.slice(0, 5).map((f) => {
              const positive = f.impact_percentage_points >= 0;
              const width = Math.min(
                Math.abs(f.impact_percentage_points) * 6,
                100,
              );
              return (
                <li key={f.feature} className="text-[13px]">
                  <div className="mb-1 flex justify-between gap-4">
                    <span className="truncate text-[var(--color-text-dim)]">
                      {f.feature.replace(/_/g, " ")}
                    </span>
                    <span>
                      {positive ? "+" : ""}
                      {f.impact_percentage_points.toFixed(1)} pts
                    </span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-[var(--color-line)]">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${width}%`,
                        background: positive
                          ? "var(--color-home)"
                          : "var(--color-away)",
                      }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </>
  );
}
