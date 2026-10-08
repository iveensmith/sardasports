/**
 * "What makes the best football prediction site?", on the home page.
 *
 * Answers a question visitors arrive with (they have searched for a "best" site, or
 * are weighing this one against others) in a few lines, and sends them to the full
 * checklist. It makes no claim to be the best; it gives the criteria and invites the
 * visitor to check this site against them. The same questions are marked up as FAQ
 * data on the checklist page itself.
 */

import Link from "next/link";

const CRITERIA = [
  "Every pick published, losses included, and downloadable",
  "Live picks kept apart from ones reconstructed after the match",
  "A sample size beside every percentage",
  "No guarantees, no “fixed matches”, no promised winnings",
];

export function GoodSite() {
  return (
    <section aria-labelledby="good-site-heading">
      <div className="max-w-[72ch]">
        <h2
          id="good-site-heading"
          className="text-[clamp(1.5rem,3vw,1.9rem)] font-bold tracking-[-0.02em]"
        >
          What makes the best football prediction site?
        </h2>
        <p className="mt-3 text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
          Whether you are comparing the best AI prediction sites or just want
          free football predictions you can trust, the question is the same: can
          you check the record? Look for these before you rely on any prediction
          site, this one included.
        </p>
        <ul className="mt-5 space-y-2.5">
          {CRITERIA.map((item) => (
            <li
              key={item}
              className="flex gap-3 text-[14.5px] leading-relaxed text-[var(--color-text-dim)]"
            >
              <span
                aria-hidden
                className="mt-[0.55em] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-gold-bright)]"
              />
              {item}
            </li>
          ))}
        </ul>
        <p className="mt-5 text-[14px]">
          <Link
            href="/best-football-prediction-site"
            className="text-[var(--color-gold-bright)] underline underline-offset-4 decoration-[var(--color-line-strong)] hover:decoration-[var(--color-gold-bright)]"
          >
            Read the full 8-point checklist
          </Link>
        </p>
      </div>
    </section>
  );
}
