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
 * So the live record is given equal billing, and the two are never blended
 * into one headline figure: a handful of live calls beside thousands of
 * backtested ones would let the blend read as a published record. The caveat
 * stays up for as long as backtested calls make up any of what is counted —
 * it is not a banner for the empty-live case, it is a statement about what
 * the number is made of, and that stays true once live calls begin to arrive.
 */

import { EngineError, getLeagues, getProgress } from "@/lib/api";
import type { Leagues } from "@/lib/discover";
import type { Progress } from "@/lib/progress";
import { lastTwelveMonths, marketName, rate } from "@/lib/progress";
import type { SettledRecord } from "@/lib/progress";
import { MonthlyTable } from "@/components/progress/MonthlyTable";
import { ProgressFaq } from "@/components/progress/ProgressFaq";
import { WinRateChart } from "@/components/progress/WinRateChart";
import { breadcrumbLd, pageMetadata, recordDatasetLd } from "@/lib/seo";
import { JsonLd } from "@/components/seo/JsonLd";

export const revalidate = 3600;

export const metadata = pageMetadata({
  title: "Football Prediction Accuracy & Full Track Record",
  description:
    "Every prediction graded against the final score: won, lost or void, with live and reconstructed picks counted apart and the full history to download.",
  path: "/progress",
});

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

/** "29 September 2026", and how long ago that was. */
function describeNewest(date: string): { label: string; daysAgo: number } {
  const day = new Date(`${date}T00:00:00Z`);
  const today = new Date();
  const daysAgo = Math.max(
    0,
    Math.floor(
      (Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()) -
        day.getTime()) /
        86_400_000,
    ),
  );
  return {
    label: day.toLocaleDateString("en-GB", {
      day: "numeric",
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }),
    daysAgo,
  };
}

function DownloadLink({
  href,
  title,
  note,
}: {
  href: string;
  title: string;
  note: string;
}) {
  return (
    <a
      href={href}
      download
      className="flex-1 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5 transition-colors hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-raised)]"
    >
      <p className="text-[14px] font-semibold">
        {title}{" "}
        <span aria-hidden className="ml-1 text-[var(--color-gold-bright)]">
          &darr;
        </span>
      </p>
      <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
        {note}
      </p>
    </a>
  );
}

export default async function ProgressPage() {
  let progress: Progress | null = null;
  let leagues: Leagues | null = null;
  let error: string | null = null;
  try {
    [progress, leagues] = await Promise.all([
      getProgress(),
      // Only for a count in the FAQ; the page does not depend on it.
      getLeagues().catch(() => null),
    ]);
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
  const hasBacktest = backtest.record.settled > 0;
  const newest = span ? describeNewest(span.last) : null;
  const recentMonths = lastTwelveMonths(progress.by_month);
  const backtestShare =
    overall.settled > 0
      ? Math.round((backtest.record.settled / overall.settled) * 100)
      : 0;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 py-12">
      <JsonLd
        data={[
          recordDatasetLd(),
          breadcrumbLd([
            { name: "Home", path: "/" },
            { name: "Track record", path: "/progress" },
          ]),
        ]}
      />
      <header className="mb-8 max-w-[72ch]">
        <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
          Every call, counted
        </p>
        <h1 className="mt-2.5 text-[clamp(1.9rem,4.5vw,2.75rem)] leading-tight font-bold tracking-[-0.02em]">
          Prediction accuracy and track record
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          Every prediction the engine has made is graded here against the final
          score: won, lost, or void where the match records no such stat. Void
          picks are excluded from every rate rather than counted either way,
          because a corners pick in a competition that logs no corners could
          never be settled.
        </p>
      </header>

      {/* The caveat, before the number it qualifies. */}
      {hasBacktest && (
        <div
          className="mb-8 rounded-[var(--radius-lg)] border p-5"
          style={{ borderColor: "var(--color-gold-dim)" }}
        >
          <p
            className="text-[14px] font-semibold"
            style={{ color: "var(--color-gold-bright)" }}
          >
            {hasLive
              ? "Most of this record is a backtest."
              : "This is a backtest, not a published record."}
          </p>
          <p className="mt-2 max-w-[72ch] text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
            {hasLive ? (
              <>
                {backtest.record.settled.toLocaleString()} of the{" "}
                {overall.settled.toLocaleString()} settled predictions (
                {backtestShare}%) were generated <em>after</em> the match was
                played, from match history truncated at kick-off. The model saw
                nothing it should not have, because the feature pipeline is
                leakage-safe and tested as such, but none of these was published
                in advance and exposed to the risk of being wrong in public.
                Only the {live.record.settled} in the live record were: stored
                before kick-off, then graded after the match. The two are
                reported separately above and never blended into one headline
                figure. The breakdowns below count both.
              </>
            ) : (
              <>
                All {backtest.record.settled} settled predictions below were
                generated <em>after</em> the match was played, from match
                history truncated at kick-off. The model saw nothing it should
                not have, because the feature pipeline is leakage-safe and
                tested as such, but none of these was published in advance and
                exposed to the risk of being wrong in public. That is weaker
                evidence than a live record, and it is labelled as such. The
                live record begins filling on its own as the board runs forward;
                nothing is backfilled into it.
              </>
            )}
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {progress.strong && progress.strong.record.settled > 0 && (
          <StatCard
            label={`Strong tips, ${progress.strong.min_probability}%+`}
            value={rate(progress.strong.record)}
            note={`${progress.strong.record.won} of ${progress.strong.record.settled} settled. Tips the engine rated ${progress.strong.min_probability}% or more before kick-off, about half of all fixtures; all tips together are ${rate(overall)}.`}
            accent="var(--color-gold-bright)"
          />
        )}
        <StatCard
          label="Backtested"
          value={hasBacktest ? rate(backtest.record) : "—"}
          note={
            hasBacktest
              ? `${backtest.record.won} of ${backtest.record.settled} settled, graded after the match`
              : "No backtested prediction on record"
          }
          accent="var(--color-gold-bright)"
        />
        <StatCard
          label="Live record"
          value={hasLive ? rate(live.record) : "—"}
          note={
            hasLive
              ? `${live.record.won} of ${live.record.settled} settled, stored before kick-off${
                  live.span ? ` since ${live.span.first}` : ""
                }`
              : "No prediction has yet been stored before kick-off"
          }
          accent={hasLive ? "var(--color-won)" : undefined}
        />
        <StatCard
          label="Settled calls"
          value={overall.settled.toLocaleString()}
          note={`${live.record.settled.toLocaleString()} live · ${backtest.record.settled.toLocaleString()} backtested${
            overall.void > 0 ? ` · ${overall.void} void, excluded` : ""
          }`}
        />
        <StatCard
          label="Span"
          value={
            span ? `${span.first.slice(0, 4)}–${span.last.slice(0, 4)}` : "—"
          }
          note={span ? `${span.first} to ${span.last}` : undefined}
        />
      </div>

      {newest && (
        <p className="mt-4 text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
          Newest settled match in the record:{" "}
          <span className="text-[var(--color-text-dim)]">{newest.label}</span>
          {newest.daysAgo > 0
            ? ` (${newest.daysAgo} ${newest.daysAgo === 1 ? "day" : "days"} ago)`
            : ""}
          .
          {newest.daysAgo >= 2
            ? " Anything played since is not in these figures."
            : ""}
        </p>
      )}

      {/*
        The reference also plots a 14-day "recent form" line. It is left out
        on purpose: the live record is one day's calls, so a daily line over
        it would be a single point, and drawing it from the backtested days
        would present a reconstruction as recent form. It becomes honest once
        the live record spans a few weeks.
      */}
      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        {recentMonths.length > 1 && (
          <WinRateChart
            months={recentMonths}
            title="Win rate by month, last 12 months"
          />
        )}
        <MonthlyTable months={progress.by_month} />
      </div>

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

      <section className="mt-8">
        <h2 className="text-[15px] font-semibold">Download the record</h2>
        <p className="mt-1.5 max-w-[68ch] text-[13px] leading-relaxed text-[var(--color-text-dim)]">
          Everything above is counted from these rows, so any figure on this
          page can be checked against them. No account needed.
        </p>
        <div className="mt-4 flex flex-col gap-4 sm:flex-row">
          <DownloadLink
            href="/progress/daily.csv"
            title="Daily record (CSV)"
            note="One row per day: won, lost, void, settled, win rate, and how many of those were live."
          />
          <DownloadLink
            href="/progress/matches.csv"
            title="Graded matches (CSV)"
            note="One row per prediction: date, competition, both teams, the call made, the outcome, and whether it was live or backtested."
          />
        </div>
      </section>

      <p className="mt-8 max-w-[72ch] text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
        Competitions and confidence buckets with fewer than ten settled calls
        are left out of the tables above, which count live and backtested calls
        together. A win rate over three fixtures is noise, and printing it
        beside a rate over six hundred would invite the two to be read as
        comparable.
      </p>

      <ProgressFaq
        backtestSpan={backtest.span}
        liveSpan={live.span}
        competitionCount={leagues?.competition_count ?? null}
      />
    </div>
  );
}
