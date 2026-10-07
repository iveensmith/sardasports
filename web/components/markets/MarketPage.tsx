/**
 * A single-market landing page: the day's fixtures ranked on one market, with
 * that market's own track record printed beside them.
 *
 * The record comes first because it is what lets a reader judge the list under
 * it. For correct score it is also the page's most important sentence — the
 * likeliest exact score is still a long shot, and a page that showed only the
 * hits would present a one-in-nine market as a reliable one. So the rate is
 * every settled call over the window, and the hits are listed beneath it, not
 * in place of it.
 *
 * Live and backtested calls are reported separately, as on the track-record
 * page. A call reconstructed after the match is evidence; it is not a forecast
 * that was ever exposed to being wrong in public.
 */

import Link from "next/link";
import { FaqItem } from "@/components/FaqItem";
import { TeamCrest } from "@/components/board/TeamCrest";
import type { Outcome } from "@/lib/board";
import type {
  MarketHit,
  MarketPageData,
  MarketPickRow,
  MarketTally,
} from "@/lib/markets";

export interface MarketCopy {
  eyebrow: string;
  title: string;
  intro: string;
  picksHeading: string;
  /** What the pick column is called. */
  pickColumn: string;
  /** One sentence on how to read the rate, shown under the record. */
  rateNote: string;
  emptyTitle: string;
  emptyBody: string;
  hitsHeading: string;
  explainerHeading: string;
  explainer: string[];
  faqs: Array<{ q: string; a: string }>;
}

function verdictColor(outcome: Outcome) {
  if (outcome === "won") return "var(--color-won)";
  if (outcome === "lost") return "var(--color-lost)";
  return "var(--color-text)";
}

function kickoff(row: MarketPickRow) {
  if (row.score) return "FT";
  return new Date(row.match_date).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function pct(value: number | null) {
  return value === null ? "—" : `${value.toFixed(1)}%`;
}

function Tally({ label, tally }: { label: string; tally: MarketTally }) {
  return (
    <div>
      <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
        {label}
      </p>
      <p className="mt-1 text-[15px] font-semibold tabular-nums">
        {pct(tally.rate)}
        <span className="ml-2 text-[12.5px] font-normal text-[var(--color-text-dim)]">
          {tally.won} of {tally.settled}
        </span>
      </p>
    </div>
  );
}

function PickRowView({ row }: { row: MarketPickRow }) {
  const { pick } = row;
  const settled = pick.outcome !== null;
  return (
    <tr className="border-t border-[var(--color-line)]">
      <td className="px-3 py-2.5 text-[11.5px] whitespace-nowrap text-[var(--color-text-faint)]">
        {kickoff(row)}
      </td>
      <td className="w-full min-w-0 px-2 py-2.5">
        <Link
          href={`/match/${row.slug}`}
          className="block min-w-0 hover:text-[var(--color-gold-bright)]"
        >
          <span className="flex items-center gap-2 text-[13px] font-semibold">
            <TeamCrest badge={row.home_badge} name={row.home_team} size={18} />
            <span className="truncate">{row.home_team}</span>
            {row.score && (
              <span className="tabular-nums">{row.score.home}</span>
            )}
          </span>
          <span className="mt-1 flex items-center gap-2 text-[13px] text-[var(--color-text-dim)]">
            <TeamCrest badge={row.away_badge} name={row.away_team} size={18} />
            <span className="truncate">{row.away_team}</span>
            {row.score && (
              <span className="tabular-nums">{row.score.away}</span>
            )}
          </span>
          <span className="mt-1 block text-[11px] text-[var(--color-text-faint)]">
            {row.competition.short_name}
            {row.competition.country ? ` · ${row.competition.country}` : ""}
          </span>
        </Link>
      </td>
      <td className="px-2 py-2.5 text-center whitespace-nowrap">
        <span
          className="block text-[13px] font-semibold"
          style={{ color: verdictColor(pick.outcome) }}
        >
          {pick.label}
          {settled && (
            <span aria-hidden className="ml-1 text-[10px]">
              {pick.outcome === "won" ? "✓" : "✕"}
            </span>
          )}
          {settled && (
            <span className="sr-only">
              {pick.outcome === "won" ? " (won)" : " (lost)"}
            </span>
          )}
        </span>
        <span className="mt-0.5 block text-[11.5px] text-[var(--color-text-dim)] tabular-nums">
          {pick.probability.toFixed(1)}%
        </span>
      </td>
      <td className="px-3 py-2.5 text-center whitespace-nowrap">
        {pick.odds !== null ? (
          <span
            className="inline-block min-w-[46px] rounded-[5px] border px-1.5 py-[3px] text-[11px] leading-none font-semibold tabular-nums"
            style={
              pick.odds_is_estimated
                ? {
                    borderColor: "var(--color-line-strong)",
                    borderStyle: "dashed",
                    color: "var(--color-text-dim)",
                  }
                : {
                    borderColor: "var(--color-line-strong)",
                    background: "var(--color-surface-raised)",
                    color: "var(--color-text-dim)",
                  }
            }
            title={
              pick.odds_is_estimated
                ? "Fair price implied by the engine's own probability — no bookmaker quoted this pick"
                : undefined
            }
          >
            {pick.odds_is_estimated ? "≈" : ""}
            {pick.odds.toFixed(2)}
          </span>
        ) : (
          <span className="text-[12px] text-[var(--color-unknown)]">—</span>
        )}
      </td>
    </tr>
  );
}

function HitRow({ hit }: { hit: MarketHit }) {
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-t border-[var(--color-line)] py-2.5 text-[13px] first:border-t-0">
      <Link
        href={`/match/${hit.match_id}`}
        className="font-medium hover:text-[var(--color-gold-bright)]"
      >
        {hit.home_team} {hit.score.home}–{hit.score.away} {hit.away_team}
      </Link>
      <span className="text-[12px] text-[var(--color-text-dim)]">
        called {hit.pick} at {hit.probability.toFixed(1)}%
        <span className="ml-2 text-[var(--color-text-faint)]">
          {hit.live ? "live" : "reconstructed"}
        </span>
      </span>
    </li>
  );
}

export function MarketPage({
  data,
  copy,
}: {
  data: MarketPageData;
  copy: MarketCopy;
}) {
  const shown = new Date(data.date).toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });
  const { record } = data;
  const hasRecord = record.overall.settled > 0;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
      <header className="mb-6 max-w-[72ch]">
        <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
          {copy.eyebrow} · {shown}
        </p>
        <h1 className="mt-2.5 text-[clamp(1.9rem,4.5vw,2.6rem)] leading-tight font-bold tracking-[-0.02em]">
          {copy.title}
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          {copy.intro}
        </p>
      </header>

      {hasRecord && (
        <section
          className="mb-8 rounded-[var(--radius-lg)] border p-5"
          style={{ borderColor: "var(--color-line-strong)" }}
          aria-label="Track record for this market"
        >
          <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
            Last {record.window_days} days, every settled call
          </p>
          <p className="mt-1.5 flex flex-wrap items-baseline gap-x-3">
            <span className="text-[28px] leading-none font-bold text-[var(--color-gold-bright)] tabular-nums">
              {pct(record.overall.rate)}
            </span>
            <span className="text-[13.5px] text-[var(--color-text-dim)]">
              {record.overall.won} of {record.overall.settled} landed
              {data.base_rate !== null &&
                ` — it lands in ${data.base_rate.toFixed(1)}% of all matches on record`}
            </span>
          </p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Tally label="Live — stored before kick-off" tally={record.live} />
            <Tally
              label="Reconstructed after the match"
              tally={record.backtest}
            />
          </div>
          <p className="mt-4 max-w-[70ch] text-[12.5px] leading-relaxed text-[var(--color-text-dim)]">
            {copy.rateNote}
          </p>
        </section>
      )}

      <section aria-label={copy.picksHeading}>
        <h2 className="text-[15px] font-semibold">{copy.picksHeading}</h2>
        {data.picks.length === 0 ? (
          <div className="mt-3 rounded-[var(--radius-lg)] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-8">
            <p className="text-[15px] font-medium">{copy.emptyTitle}</p>
            <p className="mt-2 max-w-[54ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
              {copy.emptyBody}
            </p>
          </div>
        ) : (
          <div className="mt-3 overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)]">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
                  <th className="px-3 py-2.5 font-medium">Time</th>
                  <th className="px-2 py-2.5 font-medium">Match</th>
                  <th className="px-2 py-2.5 text-center font-medium">
                    {copy.pickColumn}
                  </th>
                  <th className="px-3 py-2.5 text-center font-medium">Price</th>
                </tr>
              </thead>
              <tbody>
                {data.picks.map((row) => (
                  <PickRowView key={row.match_id} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-[12px] text-[var(--color-text-faint)]">
          {data.considered} of {data.fixtures} fixtures on this card had a view
          for this market. Prices marked ≈ are the engine&rsquo;s own fair
          price, not a bookmaker&rsquo;s.
        </p>
      </section>

      {record.recent_hits.length > 0 && (
        <section className="mt-10" aria-label={copy.hitsHeading}>
          <h2 className="text-[15px] font-semibold">{copy.hitsHeading}</h2>
          <ul className="mt-3 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] px-5 py-1">
            {record.recent_hits.map((hit) => (
              <HitRow key={hit.match_id} hit={hit} />
            ))}
          </ul>
          <p className="mt-2 text-[12px] text-[var(--color-text-faint)]">
            Only the calls that landed are listed here. The rate above counts
            the ones that did not as well.
          </p>
        </section>
      )}

      <section className="mt-12 max-w-[72ch]">
        <h2 className="text-[18px] font-bold tracking-[-0.015em]">
          {copy.explainerHeading}
        </h2>
        {copy.explainer.map((paragraph) => (
          <p
            key={paragraph}
            className="mt-3 text-[14px] leading-relaxed text-[var(--color-text-dim)]"
          >
            {paragraph}
          </p>
        ))}
      </section>

      <section className="mt-10 max-w-[72ch]">
        <h2 className="text-[18px] font-bold tracking-[-0.015em]">
          Frequently asked questions
        </h2>
        <div className="mt-4 space-y-2">
          {copy.faqs.map((item) => (
            <FaqItem key={item.q} q={item.q} a={item.a} />
          ))}
        </div>
      </section>

      <nav
        aria-label="More from UniquePredict"
        className="mt-10 flex flex-wrap gap-x-5 gap-y-2 text-[13px]"
      >
        <Link className="hover:text-[var(--color-gold-bright)]" href="/matches">
          All matches
        </Link>
        <Link className="hover:text-[var(--color-gold-bright)]" href="/bankers">
          Bankers
        </Link>
        <Link className="hover:text-[var(--color-gold-bright)]" href="/slip">
          Slip builder
        </Link>
        <Link
          className="hover:text-[var(--color-gold-bright)]"
          href="/progress"
        >
          Full track record
        </Link>
      </nav>
    </div>
  );
}
