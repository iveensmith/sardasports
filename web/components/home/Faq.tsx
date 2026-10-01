/**
 * The reference site's FAQ accordion, answered honestly in this engine's
 * own terms. Plain `<details>`/`<summary>` rather than a client component
 * with its own open/close state — an accordion is exactly what that
 * element already does, for free, with no JS and working keyboard/screen
 * reader behaviour out of the box.
 *
 * Two answers below are dynamic (real win rate, real league coverage) and
 * fall back to a qualitative line rather than a fabricated number when the
 * engine is unreachable. Every other answer is static because it describes
 * a policy, not a measurement.
 */

function Item({ q, a }: { q: string; a: string }) {
  return (
    <details className="group rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] px-5 py-4 open:pb-4">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-[14.5px] font-medium marker:content-none">
        {q}
        <span
          aria-hidden
          className="shrink-0 text-[18px] leading-none text-[var(--color-text-faint)] transition-transform group-open:rotate-45"
        >
          +
        </span>
      </summary>
      <p className="mt-3 text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
        {a}
      </p>
    </details>
  );
}

export function Faq({
  winRate,
  settled,
  competitionCount,
  countryCount,
}: {
  winRate: string | null;
  settled: number;
  competitionCount: number | null;
  countryCount: number | null;
}) {
  const accuracyAnswer =
    winRate && settled > 0
      ? `${winRate} of ${settled.toLocaleString()} settled calls have come in so far — the full history, wins and losses both, is public on the track record page. Past accuracy is not a promise about the next call.`
      : "The full history, wins and losses both, is public on the track record page — nothing here is asserted without being graded against a real result.";

  const coverageAnswer =
    competitionCount && countryCount
      ? `${competitionCount} competitions across ${countryCount} countries, from top domestic leagues down to competitions most sites skip — see the full list on the leagues page.`
      : "Every competition the engine has a trained model for — see the full list on the leagues page.";

  const items = [
    { q: "How accurate are the predictions?", a: accuracyAnswer },
    {
      q: "Do I need an account to see today's picks?",
      a: "No. Every board on this site is free to read, with no login.",
    },
    {
      q: "Can I see the picks that lost?",
      a: "Yes — the track record page shows the full history, including losses. Nothing is removed or hidden after the fact.",
    },
    {
      q: "What does the confidence score mean?",
      a: "How much the three underlying estimators agree with each other, out of 100 — not a probability of winning, and not a promise. A high-agreement call and a likely call are related but different questions.",
    },
    {
      q: "What's the “best tip” column?",
      a: "The single selection across every market this fixture supports that the engine rates furthest above that selection's own base rate — not just whichever probability happens to be highest.",
    },
    {
      q: "Can a model really predict a football match?",
      a: "Not any one match, no — no model can. This one reports a calibrated probability and is judged on whether those probabilities hold up over many matches, not on any single result.",
    },
    { q: "Which leagues and competitions are covered?", a: coverageAnswer },
    {
      q: "Does a high win rate mean I'll make money?",
      a: "No — they're different questions. A short price on a near-certainty is usually priced about right by the market already; win rate and profitability measure different things.",
    },
    {
      q: "Is this betting advice, or can I place a bet here?",
      a: "Neither. Everything here is informational, odds are shown for context only, and nothing on this site links out to a bookmaker.",
    },
    {
      q: "Do you sell fixed matches?",
      a: "No. Every pick is a real statistical estimate published before kick-off and never altered afterward.",
    },
  ];

  return (
    <section className="mt-16">
      <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
        Got questions?
      </p>
      <h2 className="mt-2.5 text-[clamp(1.5rem,3vw,1.9rem)] font-bold tracking-[-0.02em]">
        We&rsquo;ve got answers
      </h2>
      <div className="mt-6 space-y-3">
        {items.map((item) => (
          <Item key={item.q} q={item.q} a={item.a} />
        ))}
      </div>
    </section>
  );
}
