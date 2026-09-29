/**
 * The public track record.
 *
 * Every figure on this page is a count of settled calls, regraded from
 * stored predictions against final scores. Nothing here is asserted.
 *
 * The page leads with the caveat rather than burying it, because at the
 * moment the caveat is the most important fact on it: every stored
 * prediction was generated *after* the match, from history truncated at
 * kick-off. That is leakage-safe and it is still a backtest, and a
 * prediction site that shows a backtest where a reader expects a published
 * record has told them something untrue by layout alone.
 *
 * So the live record — currently empty — is given equal billing, and the
 * headline number carries the word "backtested" in the same breath. When the
 * board has run forward for a few weeks this page will have something
 * stronger to say, and it will be able to say it honestly.
 */

import { EngineError, getProgress } from "@/lib/api";
import type { Progress } from "@/lib/progress";
import { marketName, rate } from "@/lib/progress";
import type { SettledRecord } from "@/lib/progress";
import { WinRateChart } from "@/components/progress/WinRateChart";

export const revalidate = 3600;

export const metadata = {
  title: "Track record — UniquePredict",
  description:
    "Every prediction the engine has made, graded against the final score. Backtested and live records reported separately.",
};

function StatCard({
  label,
  value,
  note,
  accent,
}: {
  label: string;
  value: string;
  note?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
      <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
        {label}
      </p>
      <p
        className="mt-1.5 text-[30px] leading-none font-bold tabular-nums"
        style={accent ? { color: accent } : undefined}
      >
        {value}
      </p>
      {note && (
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
          {note}
        </p>
      )}
    </div>
  );
}

function RecordTable({
  caption,
  head,
  rows,
}: {
  caption: string;
  head: string;
  rows: Array<{ key: string; label: string; record: SettledRecord }>;
}) {
  if (rows.length === 0) return null;
  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
      <h2 className="text-[15px] font-semibold">{caption}</h2>
      <table className="mt-4 w-full text-[13px]">
        <thead>
          <tr className="text-left text-[11px] tracking-wider text-[var(--color-text-faint)] uppercase">
            <th className="pb-2 font-medium">{head}</th>
            <th className="pb-2 text-right font-medium">Won</th>
            <th className="pb-2 text-right font-medium">Lost</th>
            <th className="pb-2 text-right font-medium">Settled</th>
            <th className="pb-2 text-right font-medium">Win rate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ key, label, record }) => (
            <tr key={key} className="border-t border-[var(--color-line)]">
              <td className="py-2 text-[var(--color-text-dim)]">{label}</td>
              <td className="py-2 text-right tabular-nums">{record.won}</td>
              <td className="py-2 text-right tabular-nums">{record.lost}</td>
              <td className="py-2 text-right tabular-nums text-[var(--color-text-faint)]">
                {record.settled}
              </td>
              <td
                className="py-2 text-right font-semibold tabular-nums"
                style={{
                  color:
                    record.win_rate === null
                      ? "var(--color-unknown)"
                      : "var(--color-gold-bright)",
                }}
              >
                {rate(record)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default async function ProgressPage() {
  let progress: Progress | null = null;
  let error: string | null = null;
  try {
    progress = await getProgress();
  } catch (e) {
    error =
      e instanceof EngineError || e instanceof Error
        ? e.message
        : "The engine could not be reached.";
  }

  if (error || !progress) {
    return (
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 py-12">
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[15px] font-medium">The engine is unreachable</p>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">
            {error}
          </p>
        </div>
      </div>
    );
  }

  const { overall, live, backtest, span } = progress;
  const hasLive = live.record.settled > 0;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 py-12">
      <header className="mb-8 max-w-[72ch]">
        <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold)] uppercase">
          Every call, counted
        </p>
        <h1 className="mt-2.5 text-[clamp(1.9rem,4.5vw,2.75rem)] leading-tight font-bold tracking-[-0.02em]">
          Track record
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          Every prediction the engine has made is regraded here against the
          final score — won, lost, or void where the match records no such stat.
          Void calls are excluded from every rate rather than counted as either,
          because a corners call on a competition that logs no corners was never
          settleable.
        </p>
      </header>

      {/* The caveat, before the number it qualifies. */}
      {!hasLive && (
        <div
          className="mb-8 rounded-[var(--radius-lg)] border p-5"
          style={{ borderColor: "var(--color-gold-dim)" }}
        >
          <p
            className="text-[14px] font-semibold"
            style={{ color: "var(--color-gold-bright)" }}
          >
            This is a backtest, not a published record.
          </p>
          <p className="mt-2 max-w-[72ch] text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
            All {backtest.record.settled} settled predictions below were
            generated <em>after</em> the match was played, from match history
            truncated at kick-off. The model saw nothing it should not have —
            the feature pipeline is leakage-safe and tested as such — but none
            of these was published in advance and exposed to the risk of being
            wrong in public. That is weaker evidence than a live record and it
            is labelled as such. The live record begins filling on its own as
            the board runs forward; nothing is backfilled into it.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label={hasLive ? "Overall" : "Backtested"}
          value={rate(overall)}
          note={`${overall.won} of ${overall.settled} settled`}
          accent="var(--color-gold-bright)"
        />
        <StatCard
          label="Live record"
          value={hasLive ? rate(live.record) : "—"}
          note={
            hasLive
              ? `${live.record.won} of ${live.record.settled} settled`
              : "No prediction has yet been stored before kick-off"
          }
          accent={hasLive ? "var(--color-won)" : undefined}
        />
        <StatCard
          label="Settled calls"
          value={overall.settled.toLocaleString()}
          note={
            overall.void > 0 ? `${overall.void} void, excluded` : "none void"
          }
        />
        <StatCard
          label="Span"
          value={
            span ? `${span.first.slice(0, 4)}–${span.last.slice(0, 4)}` : "—"
          }
          note={span ? `${span.first} to ${span.last}` : undefined}
        />
      </div>

      {progress.by_month.length > 1 && (
        <div className="mt-8">
          <WinRateChart months={progress.by_month} />
        </div>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <RecordTable
          caption="By market"
          head="Market"
          rows={progress.by_market.map((m) => ({
            key: m.market,
            label: marketName(m.market),
            record: m,
          }))}
        />
        <RecordTable
          caption="By confidence"
          head="Engine confidence"
          rows={progress.by_confidence
            .filter((b) => b.settled >= 10)
            .map((b) => ({ key: b.bucket, label: b.bucket, record: b }))}
        />
      </div>

      <div className="mt-6">
        <RecordTable
          caption="By competition"
          head="Competition"
          rows={progress.by_competition
            .filter((c) => c.settled >= 10)
            .slice(0, 15)
            .map((c) => ({
              key: c.competition,
              label: c.competition,
              record: c,
            }))}
        />
      </div>

      <p className="mt-8 max-w-[72ch] text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
        Competitions and confidence buckets with fewer than ten settled calls
        are left out of the tables above. A win rate over three fixtures is
        noise, and printing it beside a rate over six hundred would invite the
        two to be read as comparable.
      </p>
    </div>
  );
}
