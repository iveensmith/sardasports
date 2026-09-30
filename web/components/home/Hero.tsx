/**
 * The landing hero: a figure, a claim, and the two ways in.
 *
 * The composition follows the reference site's, because the client asked for
 * it and it is a good one: a full-bleed figure sitting centred behind the
 * headline, dissolved into the page by a three-stop veil so the type has
 * contrast at the top and the figure has none by the bottom. Theirs runs
 * roughly 68% → 78% → 97% opacity down the frame; this uses the same shape in
 * this site's own base colour.
 *
 * Full viewport height, again matching the reference: `min-h-[calc(100svh-4rem)]`
 * accounts for the sticky header above it (`h-16`) so hero-plus-header fills
 * exactly one screen on load, the same way their negative-margin-under-a-
 * transparent-header trick does without needing a transparent header here.
 *
 * The veil and backlight are theme tokens (`--hero-veil`, `--hero-glow`),
 * not hardcoded colours — the reference's own hero is light by default, and
 * re-inks itself rather than staying dark when the reader is in dark mode.
 * This does the same: the dissolve target is always *this theme's*
 * `--color-base`, at increasing opacity, so the figure fades into whichever
 * surface is actually showing instead of into an approximated grey.
 *
 * Centred type is the exception on this site, which is left-aligned
 * everywhere else. It is earned here: the figure is symmetrical and the
 * headline sits on its shoulder line, so ranging the text left would leave
 * the composition lopsided and the figure looking like an accident.
 *
 * The lede carries the numbers in a heavier weight rather than a different
 * colour. They are the evidence, they should be the thing the eye lands on
 * second, and colouring them would put a third accent on a page that spends
 * exactly one.
 */

import Link from "next/link";
import { HeroFigure } from "@/components/home/HeroFigure";

export function Hero({
  winRate,
  settled,
  isBacktest,
  fixturesToday,
}: {
  winRate: string | null;
  settled: number;
  isBacktest: boolean;
  fixturesToday: number;
}) {
  return (
    <section className="relative isolate flex min-h-[calc(100svh-4rem)] flex-col items-center justify-center overflow-hidden">
      {/* The backlight, full-bleed. A CSS gradient rather than part of the
          SVG so it always spans the viewport — inside the SVG it was bound to
          the figure's own box and left the sides of a wide screen unlit. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-30"
        style={{ background: "var(--hero-glow)" }}
      />

      {/* The figure, height-fitted and standing on the bottom edge. `meet`
          rather than `slice`: slicing a 900-wide box into a short hero
          cropped the head clean off. `--hero-figure-opacity` is 1 in dark
          mode — flattening the SVG's own backlight and body together with
          one opacity is what made an early version invisible — but light
          mode wants the whole figure fainter, not just dissolved sooner by
          the veil, so it gets its own lower value there. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-10 bottom-0 -z-20 flex justify-center"
        style={{ opacity: "var(--hero-figure-opacity)" }}
      >
        <HeroFigure className="h-full w-auto" />
      </div>

      {/* The veil. Three stops, following the reference: it lifts off the top
          where the headline needs contrast and closes to near-solid at the
          floor so the figure dissolves rather than ending. Lighter at the top
          than the reference, because a drawn figure has less to give away
          than a photograph. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10"
        style={{ background: "var(--hero-veil)" }}
      />

      <div className="mx-auto w-full max-w-[1200px] px-4 py-16 text-center sm:px-6 lg:px-10">
        <h1 className="mx-auto max-w-[16ch] text-[clamp(2.4rem,6.4vw,4.25rem)] leading-[1.02] font-bold tracking-[-0.03em]">
          Every prediction, <span className="nt-gold-shine">graded</span>.
        </h1>

        <p className="mx-auto mt-5 max-w-[56ch] text-[clamp(0.95rem,1.6vw,1.075rem)] leading-relaxed text-[var(--color-text-dim)] text-balance">
          A calibrated engine blends three independent estimators across seven
          markets. Every call is settled against the final score
          {winRate && settled > 0 ? (
            <>
              {" "}
              &mdash;{" "}
              <b className="font-semibold text-[var(--color-text)]">
                {winRate}
              </b>{" "}
              of{" "}
              <b className="font-semibold text-[var(--color-text)]">
                {settled.toLocaleString()}
              </b>{" "}
              settled calls came in
              {isBacktest ? ", backtested" : ""}
            </>
          ) : null}
          . Today the board carries{" "}
          <b className="font-semibold text-[var(--color-text)]">
            {fixturesToday}
          </b>{" "}
          fixtures, free, with no account needed.
        </p>

        <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <Link href="#today" className="nt-cta nt-cta--primary">
            See today&rsquo;s picks
          </Link>
          <Link href="/progress" className="nt-cta nt-cta--ghost">
            Check the record
          </Link>
        </div>

        {isBacktest && (
          <p className="mx-auto mt-6 max-w-[60ch] text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
            That figure is a backtest &mdash; those predictions were generated
            after the matches from history truncated at kick-off. It is labelled
            as such everywhere it appears, and the live record starts filling on
            its own as the board runs forward.
          </p>
        )}
      </div>
    </section>
  );
}
