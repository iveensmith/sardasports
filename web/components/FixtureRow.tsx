/**
 * One fixture on the board.
 *
 * The row leads with the **forecast** — the outcome the model thinks most
 * likely — because that is what a reader means by "the prediction". It is the
 * same number the fixture's detail page shows, read off the same blended
 * probabilities, so the two pages cannot disagree.
 *
 * They used to. The row led with the highest-*expected-value* selection, so
 * Spain v Croatia showed "Away" at 14.50 while its own detail page had Spain
 * at 65%. Both figures were correct and they answered different questions,
 * but nothing on either page said so, which made the product look broken —
 * and worse, made a 14% shot read as a prediction.
 *
 * Beneath the forecast sits the spread of other markets the engine prices —
 * double chance, goals lines, both teams to score, half-time goals — each
 * with how far it sits above that selection's own base rate. Ranked on raw
 * probability these would be useless: "either team to win" is true of 73.8%
 * of all matches, so it topped 26 of 29 rows on a real card while saying
 * nothing. Lift is what makes a call a claim.
 *
 * Value still appears, because a mispriced long shot is worth surfacing. It
 * sits below the forecast, labelled "value", and never occupies the headline.
 * Where the evidence behind it is thin the row says so rather than printing a
 * "+276% expected value" the engine's own backtest (-6.74% against bookmaker
 * odds) says is not there.
 */

import Link from "next/link";
import type { BoardEntry } from "@/lib/api";
import { ConfidenceRing } from "@/components/ConfidenceRing";
import { MarketCallStrip } from "@/components/MarketCalls";

const SPORT_BADGE: Record<string, string> = {
  football: "FTB",
  basketball: "BSK",
  tennis: "TEN",
};

/** Outcome colours, so the forecast is legible at a glance and colour is
 *  never the only carrier — the label always names the outcome too. */
const OUTCOME_COLOR: Record<string, string> = {
  home: "var(--color-home)",
  draw: "var(--color-draw)",
  away: "var(--color-away)",
};

function StatusChip({ status }: { status: string }) {
  const upcoming = status === "scheduled";
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] tracking-wider uppercase">
      <span
        aria-hidden
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{
          background: upcoming ? "var(--color-gold)" : "var(--color-text-faint)",
        }}
      />
      <span style={{ color: "var(--color-text-faint)" }}>
        {upcoming ? "Pending" : status}
      </span>
    </span>
  );
}

export function FixtureRow({ fixture }: { fixture: BoardEntry }) {
  const { prediction, pick, forecast, calls } = fixture;
  const kickoff = new Date(fixture.match_date).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  // Only worth pointing out when it differs from the forecast. When value and
  // forecast agree, a second line saying the same thing is noise.
  const valueDiffers =
    pick != null &&
    forecast != null &&
    !(pick.market === "Match result" && pick.selection === forecast.selection);

  return (
    <Link
      href={`/match/${fixture.match_id}`}
      className="block rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] px-4 py-3.5 transition-colors hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-raised)]"
    >
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          {/* Meta line: badge, competition, kick-off, status. */}
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <span
              className="rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wider"
              style={{
                borderColor: "var(--color-line-strong)",
                color: "var(--color-text-faint)",
              }}
            >
              {SPORT_BADGE[fixture.sport] ?? fixture.sport.slice(0, 3).toUpperCase()}
            </span>
            <span className="truncate text-[12.5px] font-medium text-[var(--color-text-dim)]">
              {fixture.competition}
            </span>
            <span className="text-[12px] text-[var(--color-text-faint)]">
              {kickoff}
            </span>
            <span className="ml-auto">
              <StatusChip status={fixture.status} />
            </span>
          </div>

          <h3 className="mt-1.5 truncate text-[17.5px] font-semibold tracking-[-0.015em]">
            {fixture.home_team}{" "}
            <span className="font-normal text-[var(--color-text-faint)]">vs</span>{" "}
            {fixture.away_team}
          </h3>

          {/* The forecast. The headline claim of the row. */}
          {forecast ? (
            <p className="mt-1.5 flex flex-wrap items-baseline gap-x-2 text-[13px]">
              <span
                className="font-semibold"
                style={{ color: OUTCOME_COLOR[forecast.selection] }}
              >
                {forecast.label}
              </span>
              <span className="text-[var(--color-text-dim)]">
                {forecast.probability.toFixed(1)}%
              </span>
              {valueDiffers && pick && (
                <span className="text-[12.5px] text-[var(--color-text-faint)]">
                  · best price is on {pick.label} at{" "}
                  {pick.offered_price.toFixed(2)}
                  {pick.thin_evidence ? " (thin data)" : ""}
                </span>
              )}
            </p>
          ) : (
            <p className="mt-1.5 text-[13px] text-[var(--color-text-faint)]">
              The engine could not price this fixture.
            </p>
          )}

          {/* The other markets, so the row is not only "who wins". The
              match-result call is already the headline above, so it is
              dropped here rather than printed twice. */}
          {calls && (
            <MarketCallStrip
              calls={calls.by_market.filter((c) => c.market !== "match_result")}
            />
          )}

          {/* Supporting detail: why, or why not. */}
          <p className="mt-1 line-clamp-2 text-[13px] leading-[1.55] text-[var(--color-text-faint)]">
            {pick ? (
              <>
                {pick.thin_evidence && (
                  <span
                    className="mr-1.5 rounded border px-1 py-0.5 text-[10px] tracking-wide uppercase"
                    style={{
                      borderColor: "var(--color-away)",
                      color: "var(--color-away)",
                    }}
                  >
                    thin data
                  </span>
                )}
                {pick.rationale}
              </>
            ) : forecast ? (
              "No bookmaker price for this fixture, so there is nothing to compare the model against."
            ) : null}
          </p>
        </div>

        {/* Forecast price and confidence. */}
        <div className="flex shrink-0 items-center gap-3">
          {forecast && (
            <span
              className="hidden items-center overflow-hidden rounded-[var(--radius-md)] border sm:inline-flex"
              style={{ borderColor: "var(--color-line-strong)" }}
            >
              <span
                className="px-2.5 py-1.5 text-[13px] font-medium whitespace-nowrap"
                style={{ color: OUTCOME_COLOR[forecast.selection] }}
              >
                {forecast.short_label}
              </span>
              <span
                className="px-2.5 py-1.5 text-[13px] font-semibold"
                style={{
                  background: "var(--color-surface-raised)",
                  color: "var(--color-text)",
                }}
              >
                {forecast.probability.toFixed(0)}%
              </span>
            </span>
          )}

          {prediction && (
            <ConfidenceRing
              value={prediction.confidence}
              label={prediction.confidence_label}
            />
          )}
        </div>
      </div>
    </Link>
  );
}
