/**
 * The page for a sport that is not football: basketball and tennis share this.
 *
 * What it shows, in order of how much a reader needs it:
 *  1. how fresh the data is, said plainly, because some leagues' history is months old;
 *  2. the day's board, grouped by league or tournament, each prediction labelled by
 *     whether it was stored before the match or calculated afterwards;
 *  3. the record of predictions that were stored in advance and graded;
 *  4. how each model measures against the rule it has to beat, with the verdict
 *     computed from the sample size rather than asserted;
 *  5. the highest-rated competitors, the competitions covered, how it works, and
 *     the questions a reader asks.
 *
 * It never shows a figure the engine did not return, and a section with nothing to
 * show is left out rather than filled.
 */

import Link from "next/link";
import { FaqItem } from "@/components/FaqItem";
import { linkClass } from "@/components/prose/Prose";
import { JsonLd } from "@/components/seo/JsonLd";
import { SportBoard, SportDayStrip } from "@/components/sport/SportBoard";
import { SportMark } from "@/components/sport/SportMark";
import { SPORT_COPY, sportFaqs } from "@/lib/sportContent";
import {
  ageLabel,
  edgeVerdict,
  scoreline,
  shortDate,
  type OtherSportKey,
  type SportBoard as BoardData,
  type SportMatchRow,
  type SportOverview,
  type SportRecord,
} from "@/lib/sports";
import { breadcrumbLd, faqLd, matchPath } from "@/lib/seo";
import { SITE_NAME, absoluteUrl } from "@/lib/site";

const card =
  "rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)]";

function SectionTitle({
  id,
  children,
  note,
}: {
  id: string;
  children: string;
  note?: string;
}) {
  return (
    <div>
      <h2
        id={id}
        className="text-[21px] font-bold tracking-[-0.015em] scroll-mt-28"
      >
        {children}
      </h2>
      {note && (
        <p className="mt-2 max-w-[72ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
          {note}
        </p>
      )}
    </div>
  );
}

function MatchTable({
  rows,
  graded,
}: {
  rows: SportMatchRow[];
  graded: boolean;
}) {
  return (
    <div className={`${card} overflow-x-auto`}>
      <table className="w-full min-w-[560px] border-collapse text-[14px]">
        <thead>
          <tr className="text-left text-[12px] text-[var(--color-text-faint)]">
            <th className="px-4 py-3 font-medium">Date</th>
            <th className="px-4 py-3 font-medium">Match</th>
            {graded && <th className="px-4 py-3 font-medium">Result</th>}
            <th className="px-4 py-3 font-medium">Engine backs</th>
            {graded && <th className="px-4 py-3 font-medium">Verdict</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.match_id}
              className="border-t border-[var(--color-line)] align-top"
            >
              <td className="px-4 py-3 whitespace-nowrap text-[var(--color-text-dim)]">
                {shortDate(row.match_date)}
              </td>
              <td className="px-4 py-3">
                <Link
                  href={matchPath(row.home, row.away, row.match_id)}
                  className="font-medium hover:text-[var(--color-gold-bright)]"
                >
                  {row.home} v {row.away}
                </Link>
                <span className="block text-[12px] text-[var(--color-text-faint)]">
                  {row.competition}
                  {row.surface ? `, ${row.surface.toLowerCase()}` : ""}
                </span>
              </td>
              {graded && (
                <td className="px-4 py-3 whitespace-nowrap tabular-nums">
                  {scoreline(row)}
                </td>
              )}
              <td className="px-4 py-3">
                {row.pick ? (
                  <>
                    <span className="font-medium">{row.pick.name}</span>{" "}
                    <span className="tabular-nums text-[var(--color-text-dim)]">
                      {row.pick.probability.toFixed(0)}%
                    </span>
                  </>
                ) : (
                  <span className="text-[var(--color-text-faint)]">
                    Not priced
                  </span>
                )}
              </td>
              {graded && (
                <td className="px-4 py-3 whitespace-nowrap">
                  {row.pick_correct === null ? (
                    <span className="text-[var(--color-text-faint)]">–</span>
                  ) : row.pick_correct ? (
                    <span className="font-medium text-[var(--color-won)]">
                      Right
                    </span>
                  ) : (
                    <span className="font-medium text-[var(--color-lost)]">
                      Wrong
                    </span>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function pct(count: { settled: number; won: number }): string {
  return count.settled === 0
    ? "–"
    : `${((count.won / count.settled) * 100).toFixed(1)}%`;
}

function MarketsRecord({ record }: { record: SportRecord }) {
  const rows = Object.entries(record.markets ?? {}).filter(
    ([, m]) => m.live.settled + m.reconstructed.settled >= 20,
  );
  if (rows.length === 0) return null;
  return (
    <div className={`${card} overflow-x-auto`}>
      <table className="w-full min-w-[520px] border-collapse text-[14px]">
        <caption className="px-4 pt-3 text-left text-[12.5px] text-[var(--color-text-faint)]">
          How often the call the engine would back on each extra market came in
          (the line nearest a coin flip). Stored in advance is counted apart
          from reconstructed.
        </caption>
        <thead>
          <tr className="text-left text-[12px] text-[var(--color-text-faint)]">
            <th className="px-4 py-3 font-medium">Market</th>
            <th className="px-4 py-3 font-medium">Stored before the match</th>
            <th className="px-4 py-3 font-medium">Reconstructed</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([id, m]) => (
            <tr key={id} className="border-t border-[var(--color-line)]">
              <th scope="row" className="px-4 py-3 text-left font-medium">
                {m.name}
              </th>
              <td className="px-4 py-3 tabular-nums">
                {m.live.won} of {m.live.settled}{" "}
                <span className="text-[var(--color-text-dim)]">
                  ({pct(m.live)})
                </span>
              </td>
              <td className="px-4 py-3 tabular-nums">
                {m.reconstructed.won} of {m.reconstructed.settled}{" "}
                <span className="text-[var(--color-text-dim)]">
                  ({pct(m.reconstructed)})
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecordTable({
  record,
  sport,
}: {
  record: SportRecord;
  sport: OtherSportKey;
}) {
  const unit = sport === "tennis" ? "games" : "points";
  const rows = [
    { label: "Stored before the match", data: record.live },
    { label: "Reconstructed afterwards", data: record.reconstructed },
  ];
  return (
    <div className={`${card} overflow-x-auto`}>
      <table className="w-full min-w-[520px] border-collapse text-[14px]">
        <thead>
          <tr className="text-left text-[12px] text-[var(--color-text-faint)]">
            <th className="px-4 py-3 font-medium">Kind</th>
            <th className="px-4 py-3 font-medium">Winner picks</th>
            <th className="px-4 py-3 font-medium">{`Total ${unit} picks`}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.label}
              className="border-t border-[var(--color-line)] align-top"
            >
              <th scope="row" className="px-4 py-3 text-left font-medium">
                {row.label}
              </th>
              <td className="px-4 py-3 tabular-nums">
                {row.data.winner.won} of {row.data.winner.settled}{" "}
                <span className="text-[var(--color-text-dim)]">
                  ({pct(row.data.winner)})
                </span>
              </td>
              <td className="px-4 py-3 tabular-nums">
                {row.data.total.won} of {row.data.total.settled}{" "}
                <span className="text-[var(--color-text-dim)]">
                  ({pct(row.data.total)})
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-[var(--color-line)] px-4 py-3 text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
        {record.live_since
          ? `Live picks have been stored since ${shortDate(record.live_since)}, so the sample is still small. `
          : "No picks have been stored in advance and finished yet. "}
        {record.stored_total} stored in all.
      </p>
    </div>
  );
}

export function SportPage({
  sport,
  data,
  board,
  record,
  today,
}: {
  sport: OtherSportKey;
  data: SportOverview;
  board: BoardData | null;
  record: SportRecord | null;
  /** Today's date (UTC), the anchor for the day strip. */
  today: string;
}) {
  const copy = SPORT_COPY[sport];
  const faqs = sportFaqs(sport, data);
  const hasUpcoming = data.upcoming.length > 0;
  const dayHasMatches = (board?.counts.fixtures ?? 0) > 0;
  const stale = (data.days_since_last_result ?? 0) > 14;
  const plural = copy.competitor.plural;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
      <JsonLd
        data={[
          faqLd(faqs),
          breadcrumbLd([
            { name: "Home", path: "/" },
            { name: `${data.label} predictions`, path: copy.path },
          ]),
          {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            name: copy.h1,
            url: absoluteUrl(copy.path),
            isPartOf: { "@id": absoluteUrl("/#website") },
            about: data.label,
          },
        ]}
      />

      <header className="max-w-[72ch]">
        <p className="inline-flex items-center gap-2 text-[13px] font-medium text-[var(--color-text-dim)]">
          <SportMark sport={sport} size={16} />
          {data.label}
        </p>
        <h1 className="mt-2 text-[clamp(1.9rem,4.5vw,2.75rem)] leading-tight font-bold tracking-[-0.02em]">
          {copy.h1}
        </h1>
        <p className="mt-4 text-[16px] leading-relaxed text-[var(--color-text-dim)]">
          {copy.intro}
        </p>
      </header>

      {/* How fresh the data is. Always shown, and louder when it is old. */}
      <section
        aria-label="Data status"
        className={`mt-8 max-w-[900px] ${card} p-5 ${
          stale ? "border-[var(--color-line-strong)]" : ""
        }`}
      >
        <p className="text-[15px] font-semibold">
          {hasUpcoming
            ? `${data.upcoming.length}+ upcoming ${
                data.upcoming.length === 1 ? "match" : "matches"
              } priced`
            : "No upcoming matches are loaded"}
        </p>
        <p className="mt-1.5 text-[14px] leading-relaxed text-[var(--color-text-dim)]">
          The engine&rsquo;s {data.label.toLowerCase()} data holds{" "}
          <b className="font-semibold text-[var(--color-text)]">
            {data.matches_on_record.toLocaleString("en-GB")}
          </b>{" "}
          finished matches across {data.competitions.length}{" "}
          {data.competitions.length === 1 ? "competition" : "competitions"},{" "}
          {shortDate(data.first_result_date)} to{" "}
          <b className="font-semibold text-[var(--color-text)]">
            {shortDate(data.last_result_date)}
          </b>
          {stale ? ` (${ageLabel(data.days_since_last_result)} ago)` : ""}, for{" "}
          {data.competitors_on_record.toLocaleString("en-GB")} {plural}.
          {hasUpcoming
            ? ""
            : ` Nothing is scheduled in the data right now, so there is no board for the days shown below.`}
        </p>
      </section>

      <div className="mt-12 space-y-12">
        <section aria-labelledby="board" className="space-y-4">
          <SectionTitle
            id="board"
            note={
              board
                ? `${board.counts.fixtures} ${
                    board.counts.fixtures === 1 ? "match" : "matches"
                  } across ${board.counts.competitions} ${
                    board.counts.competitions === 1
                      ? "competition"
                      : "competitions"
                  }${
                    board.counts.stored_in_advance > 0
                      ? `, ${board.counts.stored_in_advance} stored before the match`
                      : ""
                  }. Times are UTC. A prediction marked "Stored in advance" was written before the match and counts towards the record below; one marked "Calculated now" is the engine's view today and does not.`
                : "The board could not be loaded just now."
            }
          >
            {board
              ? `${data.label} predictions for ${shortDate(board.date)}`
              : `${data.label} predictions`}
          </SectionTitle>
          <SportDayStrip
            sport={sport}
            active={board?.date ?? today}
            today={today}
          />
          {board && <SportBoard board={board} sport={sport} />}
        </section>

        {record && record.stored_total > 0 && (
          <section
            aria-labelledby="record"
            className="space-y-4 border-t border-[var(--color-line)] pt-9"
          >
            <SectionTitle
              id="record"
              note="Predictions stored before the match and graded against the result. Live and reconstructed are counted separately and never blended."
            >
              The record so far
            </SectionTitle>
            <RecordTable record={record} sport={sport} />
            <MarketsRecord record={record} />
          </section>
        )}

        {data.recent.length > 0 && !dayHasMatches && (
          <section
            aria-labelledby="recent"
            className="space-y-4 border-t border-[var(--color-line)] pt-9"
          >
            <SectionTitle
              id="recent"
              note="What the engine says about the latest matches on record, using only the results from before each one. These are reconstructed afterwards, not picks published in advance, so they illustrate the output and are not a track record."
            >
              The latest results, as the engine sees them
            </SectionTitle>
            <MatchTable rows={data.recent} graded />
          </section>
        )}

        {data.models.length > 0 && (
          <section
            aria-labelledby="models"
            className="space-y-4 border-t border-[var(--color-line)] pt-9"
          >
            <SectionTitle
              id="models"
              note="Accuracy on matches each model was not trained on, beside the simple rule it has to beat. A gap smaller than chance can produce is reported as no edge."
            >
              How well the models do
            </SectionTitle>
            <div className={`${card} overflow-x-auto`}>
              <table className="w-full min-w-[640px] border-collapse text-[14px]">
                <thead>
                  <tr className="text-left text-[12px] text-[var(--color-text-faint)]">
                    <th className="px-4 py-3 font-medium">Market</th>
                    <th className="px-4 py-3 font-medium">Accuracy</th>
                    <th className="px-4 py-3 font-medium">Baseline</th>
                    <th className="px-4 py-3 font-medium">Gap</th>
                    <th className="px-4 py-3 font-medium">Test matches</th>
                  </tr>
                </thead>
                <tbody>
                  {data.models.map((model) => {
                    const verdict = edgeVerdict(model);
                    return (
                      <tr
                        key={model.model}
                        className="border-t border-[var(--color-line)] align-top"
                      >
                        <th
                          scope="row"
                          className="px-4 py-3 text-left font-medium"
                        >
                          {model.label}
                        </th>
                        <td className="px-4 py-3 tabular-nums">
                          {model.accuracy.toFixed(1)}%
                        </td>
                        <td className="px-4 py-3">
                          {model.baseline === null ? (
                            <span className="text-[var(--color-text-faint)]">
                              none recorded
                            </span>
                          ) : (
                            <>
                              <span className="tabular-nums">
                                {model.baseline.toFixed(1)}%
                              </span>
                              <span className="block text-[12px] text-[var(--color-text-faint)]">
                                {model.baseline_kind}
                              </span>
                            </>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          {model.edge === null ? (
                            "–"
                          ) : (
                            <>
                              <span className="tabular-nums">
                                {model.edge >= 0 ? "+" : ""}
                                {model.edge.toFixed(1)} pts
                              </span>
                              <span
                                className={`block text-[12px] ${
                                  verdict === "clear"
                                    ? "font-medium text-[var(--color-won)]"
                                    : "text-[var(--color-text-faint)]"
                                }`}
                              >
                                {verdict === "clear"
                                  ? "Clear edge"
                                  : "No measurable edge"}
                              </span>
                            </>
                          )}
                        </td>
                        <td className="px-4 py-3 tabular-nums text-[var(--color-text-dim)]">
                          {model.test_matches?.toLocaleString("en-GB") ?? "–"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <div className="grid gap-10 border-t border-[var(--color-line)] pt-9 lg:grid-cols-2">
          {data.top_rated.length > 0 && (
            <section aria-labelledby="rated" className="space-y-4">
              <SectionTitle
                id="rated"
                note={`The highest-rated ${plural} in each competition among those active in the last year of data. Ratings only compare within one competition, so each is ranked alone.`}
              >
                {`Top-rated ${plural}`}
              </SectionTitle>
              <div className="space-y-4">
                {data.top_rated.map((group) => (
                  <div key={group.competition}>
                    <p className="mb-1.5 text-[13px] font-semibold text-[var(--color-text-dim)]">
                      {group.competition}
                    </p>
                    <ol
                      className={`${card} divide-y divide-[var(--color-line)]`}
                    >
                      {(group.teams ?? []).map((entry, index) => (
                        <li
                          key={entry.team_id}
                          className="flex items-center gap-3 px-4 py-2 text-[14px]"
                        >
                          <span className="w-5 text-[12px] tabular-nums text-[var(--color-text-faint)]">
                            {index + 1}
                          </span>
                          <span className="flex-1 font-medium">
                            {entry.name}
                          </span>
                          <span className="tabular-nums text-[var(--color-text-dim)]">
                            {entry.rating}
                          </span>
                        </li>
                      ))}
                    </ol>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section aria-labelledby="covered" className="space-y-4">
            <SectionTitle id="covered">Competitions covered</SectionTitle>
            <ul className={`${card} divide-y divide-[var(--color-line)]`}>
              {data.competitions.slice(0, 14).map((competition) => (
                <li key={competition.name} className="px-4 py-3 text-[14px]">
                  <span className="font-medium">{competition.name}</span>
                  <span className="block text-[12.5px] text-[var(--color-text-dim)]">
                    {competition.matches.toLocaleString("en-GB")} matches,{" "}
                    {shortDate(competition.first_date)} to{" "}
                    {shortDate(competition.last_date)}
                  </span>
                </li>
              ))}
            </ul>
            {data.competitions.length > 14 && (
              <p className="text-[13px] text-[var(--color-text-faint)]">
                and {data.competitions.length - 14} more, each with fewer
                matches on record.
              </p>
            )}
          </section>
        </div>

        <section
          aria-labelledby="method"
          className="max-w-[72ch] space-y-4 border-t border-[var(--color-line)] pt-9"
        >
          <SectionTitle id="method">{`How the ${data.label.toLowerCase()} predictions work`}</SectionTitle>
          <dl className="space-y-3 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
            {copy.markets.map((market) => (
              <div key={market.name}>
                <dt className="inline font-semibold text-[var(--color-text)]">
                  {market.name}.{" "}
                </dt>
                <dd className="inline">{market.body}</dd>
              </div>
            ))}
          </dl>
          {copy.method.map((paragraph) => (
            <p
              key={paragraph}
              className="text-[15px] leading-relaxed text-[var(--color-text-dim)]"
            >
              {paragraph}
            </p>
          ))}
          <p className="text-[15px] leading-relaxed text-[var(--color-text-dim)]">
            {copy.source}
          </p>
        </section>

        <section
          aria-labelledby="faq"
          className="max-w-[72ch] space-y-4 border-t border-[var(--color-line)] pt-9"
        >
          <SectionTitle id="faq">Common questions</SectionTitle>
          <div className="space-y-2">
            {faqs.map((item) => (
              <FaqItem key={item.q} q={item.q} a={item.a} />
            ))}
          </div>
        </section>

        <section className="max-w-[72ch] border-t border-[var(--color-line)] pt-9 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          <p>
            {SITE_NAME} also publishes{" "}
            <Link href="/matches" className={linkClass}>
              football predictions every day
            </Link>
            , the sport with the longest public record of picks stored before
            kick-off: see the{" "}
            <Link href="/progress" className={linkClass}>
              football track record
            </Link>{" "}
            and{" "}
            <Link href="/how-it-works" className={linkClass}>
              how the predictions are made
            </Link>
            . Predictions are probabilities, not promises, and nothing here is
            betting advice. You must be 18 or over to bet.
          </p>
        </section>
      </div>
    </div>
  );
}
