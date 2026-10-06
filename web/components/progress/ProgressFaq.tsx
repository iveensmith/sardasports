/**
 * Questions a reader of the track record is likely to ask, answered in this
 * engine's own terms.
 *
 * Two answers are dynamic (the live and backtested spans, the competition
 * count) and fall back to a qualitative line rather than a guessed figure.
 * Everything else describes how the record is built, which is a policy and
 * not a measurement.
 *
 * What is deliberately not claimed here: that the record is "published before
 * kick-off" as a whole (only the live part is), that every match ever played
 * is in it (backtested calls exist only where the engine was asked to price a
 * past fixture), or that it updates on a fixed clock (it is as current as the
 * last ingest, which is why the page prints the newest settled date).
 */

import { FaqItem } from "@/components/FaqItem";
import type { Span } from "@/lib/progress";

function monthYear(date: string): string {
  return new Date(date).toLocaleDateString("en-GB", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function ProgressFaq({
  backtestSpan,
  liveSpan,
  competitionCount,
}: {
  backtestSpan: Span | null;
  liveSpan: Span | null;
  competitionCount: number | null;
}) {
  const spanAnswer =
    backtestSpan || liveSpan
      ? [
          backtestSpan
            ? `The backtested calls cover matches from ${monthYear(backtestSpan.first)} to ${monthYear(backtestSpan.last)}.`
            : null,
          liveSpan
            ? `The live record starts on ${liveSpan.first}, the first day a fixture was predicted before it was played.`
            : "The live record has not started: no prediction has yet been stored before kick-off.",
          "Both are counted separately above, because they are not the same kind of evidence.",
        ]
          .filter(Boolean)
          .join(" ")
      : "There is nothing settled yet, so there is no span to report.";

  const coverageAnswer = competitionCount
    ? `Every stored prediction on a played fixture counts, whatever its competition — none is set aside after the fact. The engine models ${competitionCount} competitions; the Leagues page lists them with how much history sits behind each.`
    : "Every stored prediction on a played fixture counts, whatever its competition — none is set aside after the fact.";

  const items = [
    {
      q: "What do the numbers on this page count?",
      a: "Each prediction has one headline call — the likeliest thing the engine expects, chosen across the markets it prices for that fixture. That call is settled won or lost against the final score. The charts, the monthly table and both downloads are built from the same set of graded predictions, so a match cannot be in one and missing from another. The by-market table is the exception: it grades the best call in each market separately, so one match can appear in several of its rows.",
    },
    {
      q: "What is the difference between backtested and live?",
      a: "A live call was stored before kick-off, so nobody could have known the result. A backtested call was generated after the match from history cut off at kick-off: the model saw nothing it should not have, but the call was never exposed to being wrong in public. A backtest is evidence, and weaker evidence than a live record, so the two are never blended into one headline figure.",
    },
    {
      q: "Is every match the engine could have predicted in the record?",
      a: "No. Backtested calls are generated on request for past fixtures, so they are the fixtures the engine was asked to price, not every match ever played. That is not a random sample of history, and it is worth keeping in mind when reading the backtested rate.",
    },
    { q: "How long has this record been running?", a: spanAnswer },
    {
      q: "How is a call settled as won, lost or void?",
      a: "Won or lost against the final score. A call about a stat the match does not record, such as corners in a competition that logs none, is void: it was never settleable, so it is left out of every rate rather than counted as either result.",
    },
    {
      q: "When do new results appear here?",
      a: "When they have been ingested from the data provider, which is not instant. The date printed above the charts is the newest settled match in the record; anything played after it is not in these figures. The page itself is also cached for up to an hour.",
    },
    {
      q: "What do the two downloads contain?",
      a: "The daily record has one row per day: the date, how many calls were won, lost and void, how many settled, the win rate, and how many of those were live. The graded matches file has one row per prediction: the date, competition, both teams, the call we made, the outcome, and whether it was live or backtested. Neither needs an account.",
    },
    {
      q: "Why does the monthly rate jump around?",
      a: "Because a month can stand on very few calls, and a rate over a dozen of them moves a long way on a single result. That is why every rate here is printed beside its sample, and why months with nothing settled are shown as gaps rather than as zero.",
    },
    { q: "Which competitions are counted?", a: coverageAnswer },
    {
      q: "How do I check the numbers for myself?",
      a: "Download the graded matches file and count the outcomes. The won, lost and void totals match the figures at the top of this page, and the daily file sums to the same settled total.",
    },
  ];

  return (
    <section className="mt-12">
      <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
        About this record
      </p>
      <h2 className="mt-2.5 text-[clamp(1.4rem,3vw,1.75rem)] font-bold tracking-[-0.02em]">
        Questions about this page
      </h2>
      <div className="mt-6 space-y-3">
        {items.map((item) => (
          <FaqItem key={item.q} q={item.q} a={item.a} />
        ))}
      </div>
    </section>
  );
}
