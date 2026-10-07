/**
 * "How our football predictions work": three illustrated steps.
 *
 * Follows the reference site's shape and placement: a centred label and heading
 * after the "what you get" section, then three equal cards, each an inset
 * diagram with a step badge above a title and two paragraphs. The words and the
 * diagrams are this engine's own and describe what it actually does; nothing
 * here is a claim about performance, so no live number sits in it to go stale.
 * The longer version, with the markets and the grading rules, is /how-it-works.
 *
 * The steps are a true sequence (data in, cleaned, blended and graded), which is
 * the one case where numbering them says something.
 */

import Link from "next/link";
import {
  BlendDiagram,
  CleaningDiagram,
  DataCollectionDiagram,
} from "@/components/home/StepIllustrations";

const STEPS = [
  {
    step: "01",
    title: "Data collection",
    Diagram: DataCollectionDiagram,
    body: [
      "Completed matches, fixtures and final scores come from public football datasets and a licensed sports-data feed, pulled in on a schedule. Nothing is typed in by hand.",
      "Each result is kept with its competition, season and score and, where the source records them, half-time goals, corners and cards. That history is what every rating and model is built from.",
    ],
  },
  {
    step: "02",
    title: "Cleaning and validation",
    Diagram: CleaningDiagram,
    body: [
      "Raw data is not used as it arrives. Team names from different sources are matched to a single club and duplicate fixtures are merged, so a club does not appear under two names and a match is not counted twice.",
      "Where a source does not record a statistic, it is left empty rather than filled in as zero, and any market that depends on it is simply not priced for that competition.",
    ],
  },
  {
    step: "03",
    title: "Three estimators, one probability",
    Diagram: BlendDiagram,
    body: [
      "An Elo rating system, a Poisson goal model and a gradient-boosted classifier trained for each market each form their own view of the match. They are blended into one probability per outcome, and how closely they agree becomes the confidence score.",
      "Every pick is then graded against the real final score and goes on the public record, wins and losses both.",
    ],
  },
];

export function HowItWorks() {
  return (
    <section aria-labelledby="how-it-works-heading">
      <div className="text-center">
        <p className="text-[12px] font-semibold tracking-[0.18em] text-[var(--color-gold-bright)] uppercase">
          Behind the predictions
        </p>
        <h2
          id="how-it-works-heading"
          className="mt-3 text-[clamp(1.75rem,3.6vw,2.4rem)] font-bold tracking-[-0.02em]"
        >
          How our football predictions work
        </h2>
      </div>

      <div className="mt-12 grid gap-6 md:grid-cols-3">
        {STEPS.map(({ step, title, Diagram, body }) => (
          <article
            key={step}
            className="group flex flex-col overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] transition-colors duration-300 hover:border-[var(--color-line-strong)]"
          >
            <div className="relative m-3 mb-0 aspect-[16/9] overflow-hidden rounded-[var(--radius-md)] border border-[var(--color-line)] bg-[linear-gradient(160deg,var(--color-surface-raised),var(--color-surface))] px-3 pt-8 pb-3">
              <span className="absolute top-3 left-3 rounded-[6px] bg-[var(--color-gold)] px-2 py-1 text-[10.5px] leading-none font-bold tracking-wider text-[var(--color-ink-on-accent)]">
                STEP {step}
              </span>
              <Diagram />
            </div>

            <div className="flex flex-1 flex-col p-6 pt-5">
              <h3 className="text-[17px] font-semibold">{title}</h3>
              {body.map((paragraph) => (
                <p
                  key={paragraph}
                  className="mt-3 text-[14px] leading-relaxed text-[var(--color-text-dim)]"
                >
                  {paragraph}
                </p>
              ))}
            </div>
          </article>
        ))}
      </div>

      <p className="mt-6 text-center text-[13.5px] text-[var(--color-text-dim)]">
        <Link
          href="/how-it-works"
          className="text-[var(--color-gold-bright)] hover:underline"
        >
          Read the full method
        </Link>{" "}
        for the markets, the grading rules and what the numbers do not mean.
      </p>
    </section>
  );
}
