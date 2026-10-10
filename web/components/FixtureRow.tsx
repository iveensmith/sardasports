/**
 * One fixture on the board.
 *
 * **One line, one claim.** The fixture, and the selection most likely to
 * happen, sitting in the meta line after the status where the bare
 * probability used to be. Nothing else.
 *
 * Everything that used to sit under the fixture now lives on the page you
 * reach by clicking it: the market comparison, the thin-data warning, the
 * per-market breakdown. All of it is analysis, and a board is not where
 * analysis goes — it is where you find the fixture you want to read about.
 *
 * Getting here took three passes, each fixing the last one's mistake.
 * First the row led with the highest expected-value selection, so Spain v
 * Croatia showed "Away" at 14.50 while its own detail page had Spain at 65%.
 * Then it led with the likeliest match result but listed every other market
 * beside it, answering the question several times over. Then it carried the
 * prediction plus a rationale paragraph plus a thin-data badge, which is a
 * page pretending to be a row.
 *
 * Selections are named in the market's own terms — "Home or draw", not
 * "Spain or draw" — because the fixture is on the line above and a name
 * repeated immediately is width spent saying nothing.
 */

import Link from "next/link";
import type { BoardEntry } from "@/lib/api";
import { ConfidenceRing } from "@/components/ConfidenceRing";

const SPORT_BADGE: Record<string, string> = {
  football: "FTB",
  basketball: "BSK",
  tennis: "TEN",
};

/** Colour groups the kind of call. Never the only carrier — the label always
 *  names the selection in words. */
const MARKET_COLOR: Record<string, string> = {
  match_result: "var(--color-home)",
  double_chance: "var(--color-draw)",
  goals: "var(--color-gold-bright)",
  btts: "var(--color-gold-bright)",
  ht_goals: "var(--color-gold-bright)",
  corners: "var(--color-text-dim)",
  cards: "var(--color-text-dim)",
};

function StatusChip({ status }: { status: string }) {
  const upcoming = status === "scheduled";
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] tracking-wider uppercase">
      <span
        aria-hidden
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{
          background: upcoming
            ? "var(--color-gold)"
            : "var(--color-text-faint)",
        }}
      />
      <span style={{ color: "var(--color-text-faint)" }}>
        {upcoming ? "Pending" : status}
      </span>
    </span>
  );
}

export function FixtureRow({ fixture }: { fixture: BoardEntry }) {
  const { prediction, calls } = fixture;
  const call = calls?.headline ?? null;
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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
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
              {SPORT_BADGE[fixture.sport] ??
                fixture.sport.slice(0, 3).toUpperCase()}
            </span>
            <span className="truncate text-[12.5px] font-medium text-[var(--color-text-dim)]">
              {fixture.competition}
            </span>
            <span className="text-[12px] text-[var(--color-text-faint)]">
              {kickoff}
            </span>
          </div>

          <h3 className="mt-1.5 truncate text-[17.5px] font-semibold tracking-[-0.015em]">
            {fixture.home_team}{" "}
            <span className="font-normal text-[var(--color-text-faint)]">
              vs
            </span>{" "}
            {fixture.away_team}
          </h3>
        </div>

        {/* Status, then the prediction, then confidence. */}
        <div className="flex flex-wrap items-center gap-3 sm:shrink-0 sm:flex-nowrap">
          <StatusChip status={fixture.status} />

          {call ? (
            <span
              className="inline-flex items-center overflow-hidden rounded-[var(--radius-md)] border"
              style={{ borderColor: "var(--color-line-strong)" }}
            >
              <span
                className="px-2.5 py-1.5 text-[13px] font-medium whitespace-nowrap"
                style={{
                  color: MARKET_COLOR[call.market] ?? "var(--color-text)",
                }}
              >
                {call.label}
              </span>
              <span
                className="px-2.5 py-1.5 text-[13px] font-semibold"
                style={{
                  background: "var(--color-surface-raised)",
                  color: "var(--color-text)",
                }}
              >
                {call.probability.toFixed(0)}%
              </span>
            </span>
          ) : (
            <span className="text-[12.5px] text-[var(--color-text-faint)]">
              Not priced
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
