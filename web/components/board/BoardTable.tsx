/**
 * The prediction board, as a table.
 *
 * One row per fixture, one column per market: when it kicks off, who is
 * playing, the 1/X/2 prices, the engine's pick in each of three markets, the
 * one pick worth leading with, and how confident it is out of ten. Once the
 * match is played the score fills in and every pick on the row is marked won
 * or lost.
 *
 * That last part is the argument the whole product rests on. A board that
 * shows tips before kick-off and forgets them afterwards is asking to be
 * believed; one that shows yesterday's card with every pick graded has
 * earned it or not, visibly. So the graded state is not a nice-to-have on
 * this component — it is the reason it is a table rather than a list of
 * cards, because a table is what you can scan a hundred results down.
 *
 * Colour never carries a verdict alone. A settled cell shows a tick or a
 * cross as well as the colour, because green-versus-red is precisely the
 * pair a red-green colourblind reader cannot separate, and "did my tip win"
 * is not information to encode in the one channel some readers lack.
 */

import Link from "next/link";
import type { BoardRow, Outcome, Tip } from "@/lib/board";
import { kickoffLabel } from "@/lib/board";

/** Markets given their own column, matching the API's BOARD_COLUMNS. */
const COLUMNS: Array<{ market: string; heading: string }> = [
  { market: "match_result", heading: "1X2" },
  { market: "goals", heading: "O/U" },
  { market: "btts", heading: "BTTS" },
];

function outcomeStyle(outcome: Outcome) {
  if (outcome === "won") return { color: "var(--color-won)" };
  if (outcome === "lost") return { color: "var(--color-lost)" };
  if (outcome === "void") return { color: "var(--color-text-faint)" };
  return { color: "var(--color-text)" };
}

/** The non-colour half of a verdict. Nothing at all before kick-off. */
function OutcomeMark({ outcome }: { outcome: Outcome }) {
  if (outcome === null) return null;
  const mark = outcome === "won" ? "✓" : outcome === "lost" ? "✕" : "–";
  return (
    <span aria-hidden className="ml-1 text-[10px]">
      {mark}
    </span>
  );
}

function srOutcome(outcome: Outcome) {
  if (outcome === "won") return " (won)";
  if (outcome === "lost") return " (lost)";
  if (outcome === "void") return " (not settled — stat not recorded)";
  return "";
}

/** One market cell: the pick, its price beneath, and its verdict. */
function TipCell({ tip }: { tip: Tip | undefined }) {
  if (!tip) {
    return (
      <td className="px-2 py-2 text-center text-[12px] text-[var(--color-unknown)]">
        —
      </td>
    );
  }
  return (
    <td className="px-2 py-2 text-center whitespace-nowrap">
      <span
        className="text-[12.5px] font-semibold"
        style={outcomeStyle(tip.outcome)}
        title={`${tip.label} · ${tip.probability.toFixed(1)}%`}
      >
        {tip.short_label}
        <OutcomeMark outcome={tip.outcome} />
        <span className="sr-only">{srOutcome(tip.outcome)}</span>
      </span>
      <span className="block text-[11px] text-[var(--color-text-faint)]">
        {tip.odds === null ? "—" : tip.odds.toFixed(2)}
      </span>
    </td>
  );
}

/** A bare 1 / X / 2 price. */
function OddsCell({ price }: { price: number | null }) {
  return (
    <td className="px-2 py-2 text-center text-[12.5px] whitespace-nowrap text-[var(--color-text-dim)]">
      {price === null ? "—" : price.toFixed(2)}
    </td>
  );
}

function ConfidenceCell({ value }: { value: number | null }) {
  if (value === null) {
    return (
      <td className="px-2 py-2 text-center text-[12px] text-[var(--color-unknown)]">
        —
      </td>
    );
  }
  // Gold only at the top of the range, so the column has a shape a reader can
  // scan rather than nine identical highlighted numbers.
  const strong = value >= 8;
  return (
    <td className="px-2 py-2 text-center whitespace-nowrap">
      <span
        className="text-[13px] font-semibold"
        style={{
          color: strong ? "var(--color-gold-bright)" : "var(--color-text-dim)",
        }}
      >
        {value.toFixed(1)}
      </span>
      <span className="text-[10px] text-[var(--color-text-faint)]">/10</span>
    </td>
  );
}

/**
 * The fixture cell: both team names, with the score beside them.
 *
 * Names and goals are two adjacent blocks rather than one row with the score
 * pushed to the far side. This cell absorbs whatever width the numeric
 * columns leave over, so on a wide screen `justify-between` would strand the
 * score a couple of hundred pixels from the team it belongs to. Here the
 * score column sits immediately after the names and the spare width falls
 * after both.
 *
 * The names block sizes to its content rather than taking `flex-1`. With
 * `flex-1` it filled its 260px cap whatever the names were, so "Al Riyadh"
 * left almost two hundred pixels of nothing before its own scoreline. The
 * cap still truncates the long ones.
 */
function Fixture({ row }: { row: BoardRow }) {
  const played = row.score !== null;
  return (
    <div className="flex min-w-0 items-center gap-3">
      <div className="min-w-0 max-w-[260px]">
        <p className="truncate text-[13.5px] leading-tight">{row.home_team}</p>
        <p className="mt-1 truncate text-[13.5px] leading-tight">
          {row.away_team}
        </p>
      </div>
      {played && (
        <div className="shrink-0 text-right text-[13.5px] font-semibold tabular-nums">
          <p className="leading-tight">{row.score!.home}</p>
          <p className="mt-1 leading-tight">{row.score!.away}</p>
        </div>
      )}
    </div>
  );
}

function Row({ row }: { row: BoardRow }) {
  const verdict = row.best_tip?.outcome ?? null;

  return (
    <tr className="border-t border-[var(--color-line)] transition-colors hover:bg-[var(--color-surface-raised)]">
      {/* A settled row is flagged on its left edge as well as in its cells,
          so a reader skimming for losses has something to catch on. */}
      <td className="w-[52px] px-2 py-2 align-middle">
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className="h-8 w-[3px] shrink-0 rounded-full"
            style={{
              background:
                verdict === "won"
                  ? "var(--color-won)"
                  : verdict === "lost"
                    ? "var(--color-lost)"
                    : "var(--color-line-strong)",
            }}
          />
          <span className="text-[11.5px] leading-tight text-[var(--color-text-faint)]">
            {kickoffLabel(row)}
          </span>
        </div>
      </td>

      {/* `w-full` makes this the column that soaks up the table's spare
          width, so the numeric columns stay at their natural size instead of
          each being stretched a little. */}
      <td className="w-full min-w-0 px-2 py-2">
        <Link
          href={`/match/${row.slug}`}
          className="block min-w-0 hover:text-[var(--color-gold-bright)]"
        >
          <Fixture row={row} />
        </Link>
      </td>

      <OddsCell price={row.odds.home} />
      <OddsCell price={row.odds.draw} />
      <OddsCell price={row.odds.away} />

      {COLUMNS.map(({ market }) => (
        <TipCell key={market} tip={row.tips[market]} />
      ))}

      <TipCell tip={row.best_tip ?? undefined} />
      <ConfidenceCell value={row.confidence} />
    </tr>
  );
}

export function BoardTable({ rows }: { rows: BoardRow[] }) {
  if (rows.length === 0) return null;

  return (
    // Horizontal scroll rather than dropped columns: the market columns are
    // the point of the table, and a phone-width layout that hides them is a
    // different product.
    <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <table className="w-full min-w-[720px] border-collapse">
        <thead>
          <tr className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
            <th className="px-2 pb-2 text-left font-medium">Time</th>
            <th className="w-full px-2 pb-2 text-left font-medium">Match</th>
            <th className="px-2 pb-2 text-center font-medium">1</th>
            <th className="px-2 pb-2 text-center font-medium">X</th>
            <th className="px-2 pb-2 text-center font-medium">2</th>
            {COLUMNS.map(({ market, heading }) => (
              <th key={market} className="px-2 pb-2 text-center font-medium">
                {heading}
              </th>
            ))}
            <th className="px-2 pb-2 text-center font-medium">Best tip</th>
            <th className="px-2 pb-2 text-center font-medium">Conf</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <Row key={row.match_id} row={row} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
