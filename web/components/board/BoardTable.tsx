"use client";

/**
 * The prediction board, as a table.
 *
 * One row per fixture, one column per market: kick-off, the fixture with
 * both crests, the 1/X/2 prices, the engine's pick in each of three markets,
 * the one pick worth leading with, and confidence out of ten. Once the match
 * is played the score fills in and every pick on the row is marked won or
 * lost.
 *
 * That last part is the argument the whole product rests on. A board that
 * shows tips before kick-off and forgets them afterwards is asking to be
 * believed; one that shows yesterday's card with every pick graded has
 * earned it or not, visibly. So the graded state is not a nice-to-have here
 * — it is the reason this is a table rather than a list of cards, because a
 * table is what you can scan a hundred results down.
 *
 * The visual treatment follows the reference site, which gets two things
 * right that a plain table does not. Prices sit in pills, and the one the
 * engine picked is outlined, so the row shows what was chosen *and* what it
 * was chosen over. And a settled pick's price is filled with a tint of its
 * verdict, which turns the column into something read at a glance rather
 * than cell by cell.
 *
 * Colour never carries a verdict alone. Every settled cell shows a tick or a
 * cross beside the colour, screen readers get it in words, and the row
 * carries a coloured left edge as a third channel — green-versus-red is
 * precisely the pair a red-green colourblind reader cannot separate, and
 * "did my tip win" is not information to put in the one channel some readers
 * lack.
 */

import Link from "next/link";
import { useEffect, useMemo } from "react";
import type { BoardRow, Outcome, Tip } from "@/lib/board";
import { LockedBanner } from "@/components/premium/LockedBanner";
import { usePremium } from "@/components/premium/PremiumProvider";
import { LocalTime } from "@/components/LocalTime";
import { kickoffLabel } from "@/lib/board";
import { TeamCrest } from "@/components/board/TeamCrest";

/** Markets given their own column, matching the API's BOARD_COLUMNS. */
const COLUMNS: Array<{ market: string; heading: string }> = [
  { market: "match_result", heading: "1X2" },
  { market: "goals", heading: "O/U" },
  { market: "btts", heading: "BTTS" },
];

function labelColor(outcome: Outcome) {
  if (outcome === "won") return "var(--color-won)";
  if (outcome === "lost") return "var(--color-lost)";
  if (outcome === "void") return "var(--color-text-faint)";
  return "var(--color-text)";
}

/**
 * The tint behind a settled price.
 *
 * Low-alpha fills of the verdict colours rather than the colours themselves,
 * so a column of them reads as a wash a reader can scan without any single
 * cell shouting. Before kick-off there is no verdict, so there is no tint.
 */
function pillStyle(outcome: Outcome) {
  if (outcome === "won") {
    return {
      background: "color-mix(in srgb, var(--color-won) 15%, transparent)",
      borderColor: "color-mix(in srgb, var(--color-won) 38%, transparent)",
      color: "var(--color-won)",
    };
  }
  if (outcome === "lost") {
    return {
      background: "color-mix(in srgb, var(--color-lost) 14%, transparent)",
      borderColor: "color-mix(in srgb, var(--color-lost) 34%, transparent)",
      color: "var(--color-lost)",
    };
  }
  return {
    background: "var(--color-surface-raised)",
    borderColor: "var(--color-line-strong)",
    color: "var(--color-text-dim)",
  };
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

function srOutcome(outcome: Outcome, market?: string) {
  if (outcome === "won") return " (won)";
  if (outcome === "lost") return " (lost)";
  if (outcome === "void") {
    // Draw no bet returns the stake on a draw; elsewhere a void is a statistic nobody recorded.
    return market === "dnb"
      ? " (draw: stake returned)"
      : "  (not settled: stat not recorded)";
  }
  return "";
}

/** One market cell: the pick above, its price in a pill below. */
function TipCell({
  tip,
  markStrong = false,
}: {
  tip: Tip | undefined;
  markStrong?: boolean;
}) {
  if (!tip) {
    return (
      <td className="px-1.5 py-2 text-center text-[12px] text-[var(--color-unknown)]">
        —
      </td>
    );
  }
  return (
    <td className="px-1.5 py-2 text-center whitespace-nowrap">
      <span
        className="block text-[12.5px] leading-tight font-semibold"
        style={{ color: labelColor(tip.outcome) }}
        title={`${tip.label} · ${tip.probability.toFixed(1)}%`}
      >
        {tip.short_label}
        <OutcomeMark outcome={tip.outcome} />
        <span className="sr-only">{srOutcome(tip.outcome, tip.market)}</span>
        {markStrong && tip.strong && (
          <span
            className="ml-1 text-[10px] text-[var(--color-gold-bright)]"
            title="Strong tip: the engine rates this 70% or more"
          >
            <span aria-hidden="true">★</span>
            <span className="sr-only"> (strong tip)</span>
          </span>
        )}
      </span>
      {tip.odds !== null ? (
        <span
          className="mt-1 inline-block min-w-[46px] rounded-[5px] border px-1.5 py-[3px] text-[11px] leading-none font-semibold tabular-nums"
          style={
            tip.odds_is_estimated
              ? {
                  borderColor: "var(--color-line-strong)",
                  borderStyle: "dashed",
                  color: "var(--color-text-dim)",
                }
              : pillStyle(tip.outcome)
          }
          title={
            tip.odds_is_estimated
              ? "Fair price implied by the engine's own probability. No bookmaker quoted this pick."
              : undefined
          }
        >
          {tip.odds_is_estimated ? "≈" : ""}
          {tip.odds.toFixed(2)}
        </span>
      ) : (
        <span className="mt-1 block text-[11px] text-[var(--color-text-faint)]">
          —
        </span>
      )}
    </td>
  );
}

/**
 * A 1 / X / 2 price.
 *
 * Outlined when it is the selection the engine picked, so the row shows not
 * just what was chosen but what it was chosen over — which is most of what
 * makes a price column worth printing.
 */
function OddsCell({
  price,
  picked,
  estimated = false,
}: {
  price: number | null;
  picked: boolean;
  estimated?: boolean;
}) {
  if (price === null) {
    return (
      <td className="px-1.5 py-2 text-center text-[12px] text-[var(--color-unknown)]">
        —
      </td>
    );
  }
  return (
    <td className="px-1.5 py-2 text-center whitespace-nowrap">
      {/* Same stack as TipCell — an (empty) pick line above the price, and a
          price pill of the same size — so these three pills sit on one line
          with the prices in the market columns instead of floating above them. */}
      <span
        aria-hidden="true"
        className="block text-[12.5px] leading-tight select-none"
      >
        &nbsp;
      </span>
      <span
        className="mt-1 inline-block min-w-[46px] rounded-[5px] border px-1.5 py-[3px] text-[11px] leading-none font-semibold tabular-nums"
        style={
          picked
            ? {
                borderColor: "var(--color-gold-dim)",
                background:
                  "color-mix(in srgb, var(--color-gold) 10%, transparent)",
                color: "var(--color-text)",
              }
            : {
                borderColor: "var(--color-line)",
                color: "var(--color-text-dim)",
              }
        }
        title={
          estimated
            ? "Fair price implied by the engine's own probability. No bookmaker quoted this price."
            : undefined
        }
      >
        {estimated ? "≈" : ""}
        {price.toFixed(2)}
      </span>
    </td>
  );
}

function ConfidenceCell({ value }: { value: number | null }) {
  if (value === null) {
    return (
      <td className="px-1.5 py-2 text-center text-[12px] text-[var(--color-unknown)]">
        —
      </td>
    );
  }
  // Gold only at the top of the range, so the column has a shape a reader can
  // scan rather than nine identical highlighted numbers.
  const strong = value >= 8;
  const color = strong ? "var(--color-gold-bright)" : "var(--color-text-dim)";
  // The ring is the score drawn: an arc from twelve o'clock, clockwise, as long
  // as value/10 of the circle — a 10 closes it, a 9.3 stops just short. It has
  // the number's own colour and no background track, so what is drawn is only
  // what was scored. `pathLength` makes the dash arithmetic a plain percentage.
  const filled = Math.min(Math.max(value, 0), 10) * 10;
  return (
    <td className="px-1.5 py-2 text-center whitespace-nowrap">
      <span
        className="relative inline-flex h-[34px] w-[34px] items-center justify-center"
        title={`Estimator agreement ranks ${value.toFixed(1)} out of 10 against past fixtures (5 is typical)`}
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 34 34"
          className="absolute inset-0 -rotate-90"
        >
          <circle
            cx="17"
            cy="17"
            r="15"
            fill="none"
            stroke={color}
            strokeWidth="2.5"
            strokeLinecap="round"
            pathLength={100}
            strokeDasharray={`${filled} 100`}
          />
        </svg>
        <span className="text-[13px] font-bold tabular-nums" style={{ color }}>
          {value.toFixed(1)}
        </span>
      </span>
    </td>
  );
}

/**
 * The fixture cell: both crests, both names, and the score beside them.
 *
 * Names and goals are adjacent blocks rather than one row with the score
 * pushed to the far side. This cell absorbs whatever width the numeric
 * columns leave over, so `justify-between` would strand the score a couple
 * of hundred pixels from the team it belongs to.
 *
 * The home side is set a shade brighter than the away side — once the crests
 * are in, it is the only thing left saying which is which, and it costs
 * nothing.
 */
function Fixture({ row }: { row: BoardRow }) {
  const played = row.score !== null;
  const live = !played ? (row.live ?? null) : null;
  return (
    <div className="flex min-w-0 items-center gap-3">
      <div className="min-w-0 max-w-[260px]">
        <p className="flex items-center gap-2 text-[13.5px] leading-tight">
          <TeamCrest badge={row.home_badge} name={row.home_team} />
          <span className="truncate font-medium text-[var(--color-text)]">
            {row.home_team}
          </span>
        </p>
        <p className="mt-1.5 flex items-center gap-2 text-[13.5px] leading-tight">
          <TeamCrest badge={row.away_badge} name={row.away_team} />
          <span className="truncate text-[var(--color-text-dim)]">
            {row.away_team}
          </span>
        </p>
      </div>
      {played && (
        <div className="shrink-0 text-right text-[13.5px] font-semibold tabular-nums">
          <p className="leading-tight">{row.score!.home}</p>
          <p className="mt-1.5 leading-tight">{row.score!.away}</p>
        </div>
      )}
      {live && (
        <div
          className="shrink-0 text-right text-[13.5px] font-semibold tabular-nums"
          style={{ color: "var(--color-lost)" }}
        >
          <p className="leading-tight">{live.home}</p>
          <p className="mt-1.5 leading-tight">{live.away}</p>
        </div>
      )}
    </div>
  );
}

/**
 * Where a locked row's prediction would be: a blur in the shape of a pick (or of the confidence
 * ring), linking to the plans. There is nothing behind it: the engine did not send the pick.
 */
function LockedCell({ shape }: { shape: "pick" | "ring" }) {
  return (
    <td className="px-1.5 py-2 text-center">
      <Link
        href="/premium"
        prefetch={false}
        title="Premium members only. Unlock all predictions"
        className="inline-flex flex-col items-center gap-1 select-none"
      >
        {shape === "pick" ? (
          <>
            <span aria-hidden className="h-[13px] w-[30px] rounded bg-[var(--color-text-faint)]/45 blur-[3.5px]" />
            <span aria-hidden className="h-[17px] w-[44px] rounded-[5px] bg-[var(--color-text-faint)]/30 blur-[3.5px]" />
          </>
        ) : (
          <span aria-hidden className="h-[28px] w-[28px] rounded-full bg-[var(--color-text-faint)]/35 blur-[3.5px]" />
        )}
        <span className="sr-only">Locked. Premium members only.</span>
      </Link>
    </td>
  );
}

function Row({ row }: { row: BoardRow }) {
  const verdict = row.best_tip?.outcome ?? null;
  const picked = row.tips.match_result?.selection ?? null;

  return (
    <tr className="border-t border-[var(--color-line)] transition-colors hover:bg-[var(--color-surface-raised)]">
      {/* A settled row is flagged on its left edge as well as in its cells,
          so a reader skimming for losses has something to catch on. */}
      <td className="w-[56px] px-1.5 py-2 align-middle">
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className="h-9 w-[3px] shrink-0 rounded-full"
            style={{
              background:
                verdict === "won"
                  ? "var(--color-won)"
                  : verdict === "lost"
                    ? "var(--color-lost)"
                    : "var(--color-line-strong)",
            }}
          />
          {row.live && row.score === null ? (
            <span
              className="text-[11.5px] leading-tight font-semibold"
              style={{ color: "var(--color-lost)" }}
            >
              <span className="sr-only">Live, </span>
              <span aria-hidden>LIVE </span>
              {row.live.label}
            </span>
          ) : (
            <span className="text-[11.5px] leading-tight text-[var(--color-text-faint)]">
              {row.score ? (
                kickoffLabel(row)
              ) : (
                <LocalTime iso={row.match_date} />
              )}
            </span>
          )}
        </div>
      </td>

      {/* `sm:w-full` makes this the column that soaks up the table's spare
          width, so the numeric columns keep their natural size instead of each
          being stretched a little. Below `sm` it stays at its content width,
          which brings the prices into the first view on a phone. */}
      <td className="min-w-0 px-2 py-2 sm:w-full">
        <Link
          href={`/match/${row.slug}`}
          className="block min-w-0 hover:text-[var(--color-gold-bright)]"
        >
          <Fixture row={row} />
        </Link>
      </td>

      <OddsCell
        price={row.odds.home}
        picked={picked === "home"}
        estimated={row.odds_estimated.home}
      />
      <OddsCell
        price={row.odds.draw}
        picked={picked === "draw"}
        estimated={row.odds_estimated.draw}
      />
      <OddsCell
        price={row.odds.away}
        picked={picked === "away"}
        estimated={row.odds_estimated.away}
      />

      {row.locked ? (
        <>
          {COLUMNS.map(({ market }) => (
            <LockedCell key={market} shape="pick" />
          ))}
          <LockedCell shape="pick" />
          <LockedCell shape="ring" />
        </>
      ) : (
        <>
          {COLUMNS.map(({ market }) => (
            <TipCell key={market} tip={row.tips[market]} />
          ))}

          <TipCell tip={row.best_tip ?? undefined} markStrong />
          <ConfidenceCell value={row.confidence} />
        </>
      )}
    </tr>
  );
}

/**
 * Edge shadows that appear only while there is more table to scroll to.
 *
 * On a phone the picks sit to the right of the fixture, off screen, and a thin
 * scrollbar is the only sign of them. The two `local` layers are covers that
 * travel with the content and hide the matching `scroll` shadow once the edge
 * is reached, so a shadow shows exactly where something is still hidden. Pure
 * CSS: no scroll listener, nothing to re-render.
 */
const SCROLL_EDGES = {
  background: [
    "linear-gradient(to right, var(--color-surface) 30%, transparent) left center / 36px 100% no-repeat local",
    "linear-gradient(to left, var(--color-surface) 30%, transparent) right center / 36px 100% no-repeat local",
    "radial-gradient(farthest-side at 0 50%, var(--color-line-strong), transparent) left center / 14px 100% no-repeat scroll",
    "radial-gradient(farthest-side at 100% 50%, var(--color-line-strong), transparent) right center / 14px 100% no-repeat scroll",
  ].join(", "),
} as const;

export function BoardTable({
  rows,
  banner = true,
}: {
  rows: BoardRow[];
  /** Say, above the rows, that some are locked. A page with several tables turns this off and
   * says it once itself (see `LockedBanner`). */
  banner?: boolean;
}) {
  const { premium, rows: unlocked, unlock } = usePremium();
  const lockedIds = useMemo(
    () => rows.filter((row) => row.locked).map((row) => row.match_id),
    [rows],
  );
  // A premium member's browser fetches what the page was sent without.
  useEffect(() => {
    if (premium && lockedIds.length > 0) unlock(lockedIds);
  }, [premium, lockedIds, unlock]);
  const shown = useMemo(
    () => rows.map((row) => (row.locked && unlocked[row.match_id]) || row),
    [rows, unlocked],
  );
  const stillLocked = shown.filter((row) => row.locked).length;

  if (rows.length === 0) return null;

  return (
    // A bordered card, matching every other grouped listing on the site
    // (the leagues page's country blocks, the bankers record panel). The
    // border lives on this wrapper rather than `overflow-x-auto`'s own div,
    // so the rounded corners clip the table's background instead of getting
    // squared off by it.
    <div className="overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)]">
      {banner && <LockedBanner count={stillLocked} />}
      {/* Horizontal scroll rather than dropped columns: the market columns
          are the point of the table, and a phone-width layout that hides
          them is a different product. */}
      <div
        className="overflow-x-auto px-4 py-3 sm:px-5 sm:py-4"
        style={SCROLL_EDGES}
      >
        <table className="w-full border-collapse sm:min-w-[760px]">
          <thead>
            <tr className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
              <th
                className="px-1.5 pb-2 text-left font-medium"
                title="Kick-off, in your own time zone"
              >
                Time
              </th>
              <th className="px-2 pb-2 text-left font-medium sm:w-full">
                Match
              </th>
              <th className="px-1.5 pb-2 text-center font-medium">1</th>
              <th className="px-1.5 pb-2 text-center font-medium">X</th>
              <th className="px-1.5 pb-2 text-center font-medium">2</th>
              {COLUMNS.map(({ market, heading }) => (
                <th
                  key={market}
                  className="px-1.5 pb-2 text-center font-medium"
                >
                  {heading}
                </th>
              ))}
              <th className="px-1.5 pb-2 text-center font-medium">Best tip</th>
              <th className="px-1.5 pb-2 text-center font-medium">Conf</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <Row key={row.match_id} row={row} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
