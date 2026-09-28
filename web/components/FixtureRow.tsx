/**
 * One fixture on the board.
 *
 * Layout follows the reference the client supplied: a sport badge and meta
 * line, the fixture in large type, a one-line rationale beneath it, then the
 * pick with its price and a confidence ring on the right.
 *
 * The one thing deliberately *not* copied is an unqualified expected-value
 * figure. The engine's own backtest returns -6.74% against bookmaker odds,
 * and most of today's fixtures are internationals where a competitor may
 * have ten matches of history — so a bare "+276% expected value" would be
 * the most misleading thing on the page. Where the evidence is thin the row
 * says so, and the value figure is shown muted rather than as a headline.
 */

import Link from "next/link";
import type { BoardEntry } from "@/lib/api";
import { ConfidenceRing } from "@/components/ConfidenceRing";

const SPORT_BADGE: Record<string, string> = {
  football: "FTB",
  basketball: "BSK",
  tennis: "TEN",
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
  const { prediction, pick } = fixture;
  const kickoff = new Date(fixture.match_date).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

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
            ) : prediction ? (
              "No bookmaker price for this fixture, so there is nothing to compare the model against."
            ) : (
              "The engine could not price this fixture."
            )}
          </p>
        </div>

        {/* Pick and confidence. */}
        <div className="flex shrink-0 items-center gap-3">
          {pick && (
            <span
              className="hidden items-center overflow-hidden rounded-[var(--radius-md)] border sm:inline-flex"
              style={{ borderColor: "var(--color-line-strong)" }}
            >
              <span className="px-2.5 py-1.5 text-[13px] font-medium whitespace-nowrap">
                {pick.label}
              </span>
              <span
                className="px-2.5 py-1.5 text-[13px] font-semibold"
                style={{
                  background: "var(--color-surface-raised)",
                  // Muted unless the value is both positive and evidenced.
                  color:
                    pick.positive_value && !pick.thin_evidence
                      ? "var(--color-gold-bright)"
                      : "var(--color-text-dim)",
                }}
              >
                {pick.offered_price.toFixed(2)}
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
