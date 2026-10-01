/**
 * The reference site's own three-step "how it works" explainer, in this
 * engine's actual terms rather than its wording. No live numbers here —
 * this is process, not a claim about performance, so it stays static
 * rather than reaching for a count that would go stale the day it's
 * fetched.
 */

const STEPS = [
  {
    step: "01",
    title: "Ingest real results",
    body: "Decades of historical results per competition, plus live fixtures, odds and final scores pulled in on a schedule from a licensed sports-data API — never typed in by hand.",
  },
  {
    step: "02",
    title: "Engineer leakage-safe features",
    body: "Elo ratings, rolling form, head-to-head history, corner and card rates — every feature computed strictly from what was known before kick-off, checked against the training pipeline so nothing from after the final whistle leaks in.",
  },
  {
    step: "03",
    title: "Blend three independent models",
    body: "An Elo rating system, a Poisson goal model, and a gradient-boosted classifier trained per market are blended into one probability, then settled against the real final score — win or lose, the call stays on the record.",
  },
];

export function HowItWorks() {
  return (
    <section className="mt-16">
      <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
        Behind the predictions
      </p>
      <h2 className="mt-2.5 text-[clamp(1.5rem,3vw,1.9rem)] font-bold tracking-[-0.02em]">
        How this engine works
      </h2>
      <div className="mt-6 grid gap-4 md:grid-cols-3">
        {STEPS.map((s) => (
          <div
            key={s.step}
            className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5"
          >
            <span
              className="text-[12px] font-bold tracking-wider"
              style={{ color: "var(--color-gold-bright)" }}
            >
              STEP {s.step}
            </span>
            <h3 className="mt-2 text-[15.5px] font-semibold">{s.title}</h3>
            <p className="mt-2 text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
              {s.body}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
