/**
 * One fixture on the board.
 *
 * **One prediction per row: the selection most likely to happen**, taken
 * across every market the engine prices — match result, double chance, goals
 * lines, both teams to score, half-time goals, corners and cards. Nothing
 * else on the row competes with it for the reader's eye.
 *
 * Getting here took two wrong turns, both worth recording.
 *
 * First the row led with the highest *expected-value* selection, so Spain v
 * Croatia showed "Away" at 14.50 while its own detail page had Spain at 65%.
 * Both were right and they answered different questions, but nothing said so,
 * which made a 14% shot read as a prediction.
 *
 * Then it led with the most likely *match result* and listed the other
 * markets beside it, which answered the question several times over. A row
 * should make one claim.
 *
 * So: the likeliest call, and its probability. Because "likeliest" and
 * "most informative" are not the same thing — "either team to win" lands
 * 73.8% of all matches on its own — the call carries its base rate as quiet
 * context. That never changes which prediction is made; it lets a reader tell
 * a 76% that means something from a 76% that was always going to be true.
 *
 * The price line below is about the market, not the fixture, and says so.
 */

import Link from "next/link";
import type { BoardEntry } from "@/lib/api";
import { ConfidenceRing } from "@/components/ConfidenceRing";

const SPORT_BADGE: Record<string, string> = {
  football: "FTB",
  basketball: "BSK",
  tennis: "TEN",
};

/** Outcome colours. Colour is never the only carrier — the label always
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
  const { prediction, pick, calls } = fixture;
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

          {/* The prediction. The only claim this row makes. */}
          {call ? (
            <p className="mt-1.5 flex flex-wrap items-baseline gap-x-2 text-[14px]">
              <span
                className="font-semibold"
                style={{ color: MARKET_COLOR[call.market] ?? "var(--color-text)" }}
              >
                {call.label}
              </span>
              <span className="font-semibold text-[var(--color-text)]">
                {call.probability.toFixed(1)}%
              </span>
              {call.base_rate !== null && (
                <span className="text-[12px] text-[var(--color-text-faint)]">
                  {call.market_name.toLowerCase()} · lands{" "}
                  {call.base_rate.toFixed(0)}% of the time normally
                </span>
              )}
            </p>
          ) : (
            <p className="mt-1.5 text-[13px] text-[var(--color-text-faint)]">
              The engine could not price this fixture.
            </p>
          )}

          {/* The market, which is a different subject and is labelled as one. */}
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
            ) : call ? (
              "No bookmaker price for this fixture, so there is nothing to compare the model against."
            ) : null}
          </p>
        </div>

        {/* The same prediction's probability, and the engine's confidence in
            the fixture as a whole. */}
        <div className="flex shrink-0 items-center gap-3">
          {call && (
            <span
              className="hidden items-center overflow-hidden rounded-[var(--radius-md)] border sm:inline-flex"
              style={{ borderColor: "var(--color-line-strong)" }}
            >
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
