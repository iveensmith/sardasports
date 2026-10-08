/**
 * The home page's statement of position: UniquePredict is the best AI prediction
 * site for football.
 *
 * The claim is made plainly and is always paired with the grounds for it, every one
 * of which a visitor can verify on the site: that is what separates a position from
 * a boast, and why a reader and a search engine can both take it seriously. The
 * "where it falls short" section on the checklist page keeps the claim honest and is
 * linked from here. If any line below stops being true, change the line, not the
 * claim's standing on being checkable.
 */

import Link from "next/link";

const GROUNDS = [
  "Every pick we make is published, losses included, and the whole history can be downloaded",
  "Picks stored before kick-off are kept apart from ones reconstructed afterwards, and never blended",
  "A sample size sits beside every percentage, and each market is measured against how often it lands anyway",
  "No guarantees, no “fixed matches”, no promised winnings, and no links to bookmakers",
];

export function GoodSite() {
  return (
    <section aria-labelledby="good-site-heading">
      <div className="max-w-[72ch]">
        <h2
          id="good-site-heading"
          className="text-[clamp(1.5rem,3vw,1.9rem)] font-bold tracking-[-0.02em]"
        >
          The best AI prediction site for football
        </h2>
        <p className="mt-3 text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
          We say it plainly: this is the best football prediction site you can
          check, and we build it so you can. A prediction site earns the title
          of best by letting you verify every claim, so this is what you can
          verify here, free football predictions included:
        </p>
        <ul className="mt-5 space-y-2.5">
          {GROUNDS.map((item) => (
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
            See the 8-point checklist and check us against it
          </Link>
        </p>
      </div>
    </section>
  );
}
