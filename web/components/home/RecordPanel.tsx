/**
 * The framed panel under "Browse by sport": the record, in numbers.
 *
 * It sits where a paid-plans block would sit on a betting site. There are no plans
 * here (the site is free and has no accounts), so the same visual weight goes to the
 * thing the site actually has to sell: how its picks have done. Each tile is a count
 * the progress page also shows, with the same two kinds of record kept apart: picks
 * stored before kick-off, and picks reconstructed afterwards from history cut off at
 * kick-off. A tile with nothing behind it is not drawn.
 */

import Link from "next/link";
import { ArrowRight, Trophy } from "@/components/home/icons";
import { rate, type SettledRecord } from "@/lib/progress";

function Tile({
  label,
  record,
  note,
  emphasis = false,
}: {
  label: string;
  record: SettledRecord;
  note: string;
  emphasis?: boolean;
}) {
  return (
    <div
      className={`rounded-[12px] border p-4 text-center ${
        emphasis
          ? "border-[var(--color-gold)]/70 bg-[var(--color-gold)]/[0.07]"
          : "border-[var(--color-line-strong)] bg-[var(--color-surface-raised)]"
      }`}
    >
      <p className="text-[11px] font-extrabold tracking-[0.12em] text-[var(--color-text-dim)] uppercase">
        {label}
      </p>
      <p className="mt-2 text-[clamp(1.6rem,3.4vw,2.15rem)] leading-none font-black tracking-[-0.02em] text-[var(--color-gold-bright)] tabular-nums">
        {rate(record)}
      </p>
      <p className="mt-2 text-[12.5px] leading-snug text-[var(--color-text-dim)] tabular-nums">
        {record.won.toLocaleString("en-GB")} of{" "}
        {record.settled.toLocaleString("en-GB")} {note}
      </p>
    </div>
  );
}

export function RecordPanel({
  live,
  strong,
  backtest,
}: {
  live: SettledRecord | null;
  strong: { record: SettledRecord; minProbability: number } | null;
  backtest: SettledRecord | null;
}) {
  const tiles = [
    live && (
      <Tile
        key="live"
        emphasis
        label="Live record"
        record={live}
        note="picks won, stored before kick-off"
      />
    ),
    strong && strong.record.settled > 0 && (
      <Tile
        key="strong"
        label={`Strong tips, ${strong.minProbability}%+`}
        record={strong.record}
        note="strong tips won"
      />
    ),
    backtest && (
      <Tile
        key="backtest"
        label="Reconstructed"
        record={backtest}
        note="rebuilt from past matches"
      />
    ),
  ].filter(Boolean);

  if (tiles.length === 0) return null;

  return (
    <section aria-labelledby="record-panel">
      <div className="relative overflow-hidden rounded-[18px] border-2 border-[var(--color-gold)]/80 bg-[var(--color-surface)] p-5 sm:p-7">
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(60% 120% at 0% 0%, rgba(245,192,0,0.13), transparent 62%)",
          }}
        />
        <div className="relative grid items-center gap-6 lg:grid-cols-[1fr_1.45fr] lg:gap-10">
          <div>
            <p className="flex items-center gap-3 text-[15px] font-black tracking-[0.04em] uppercase">
              <span className="flex h-11 w-11 items-center justify-center rounded-full border-2 border-[var(--color-gold)] text-[var(--color-gold-bright)]">
                <Trophy size={22} />
              </span>
              <span>
                SARDA<span className="text-[var(--color-gold)]">SPORTS</span>
              </span>
            </p>
            <h2
              id="record-panel"
              className="mt-3 text-[clamp(1.9rem,4.4vw,2.9rem)] leading-[0.95] font-black tracking-[-0.03em] text-[var(--color-gold)] uppercase"
            >
              The record
            </h2>
            <p className="mt-2 text-[17px] font-semibold">
              Every pick graded. Win or lose.
            </p>
            <p className="mt-2 max-w-[44ch] text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
              Picks are saved before kick-off and settled against the final score.
              Live picks and picks rebuilt from history are counted apart and
              never blended.
            </p>
            <Link href="/progress" className="nt-cta nt-cta--primary mt-5">
              See the full record
              <ArrowRight size={18} />
            </Link>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">{tiles}</div>
        </div>
      </div>
    </section>
  );
}
