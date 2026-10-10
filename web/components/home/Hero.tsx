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
 * Full viewport height, again matching the reference: `min-h-[calc(100svh-6.5rem)]`
 * accounts for the sticky header above it (`h-16` plus the 2.5rem sport tabs) so hero-plus-header fills
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
import { rate, type SettledRecord } from "@/lib/progress";

/** Below this many settled picks a win rate moves a long way on one result. */
const SMALL_SAMPLE = 100;

export function Hero({
  live,
  backtest,
  liveSince,
  fixturesToday,
  strong = null,
}: {
  /** Picks stored before kick-off, then graded. Null before any exist. */
  live: SettledRecord | null;
  /** Picks reconstructed after the match from history cut off at kick-off. */
  backtest: SettledRecord | null;
  liveSince: string | null;
  fixturesToday: number;
  /** The tips the engine rated at least `minProbability` before kick-off: a subset of the above. */
  strong?: { record: SettledRecord; minProbability: number } | null;
}) {
  return (
    <section className="relative isolate flex min-h-[calc(100svh-6.5rem)] flex-col items-center justify-center overflow-hidden">
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
        {/* The H1 carries the page's main search phrase. It used to be "Every
            prediction, graded.", which is a good line and says nothing a
            searcher typed. The idea survives as the second half. */}
        <h1 className="mx-auto max-w-[19ch] text-[clamp(2.2rem,5.8vw,3.9rem)] leading-[1.04] font-bold tracking-[-0.03em]">
          Football predictions, every one{" "}
          <span className="nt-gold-shine">graded</span>.
        </h1>

        <p className="mx-auto mt-5 max-w-[56ch] text-[clamp(0.95rem,1.6vw,1.075rem)] leading-relaxed text-[var(--color-text-dim)] text-balance">
          The best AI prediction site for football: free predictions and betting
          tips from a calibrated engine that blends three independent estimators
          across seven markets. Every pick is graded against the final score and
          stays on the record, win or lose. Today&rsquo;s board covers{" "}
          <b className="font-semibold text-[var(--color-text)]">
            {fixturesToday}
          </b>{" "}
          {fixturesToday === 1 ? "fixture" : "fixtures"}, free, with no account
          needed.
        </p>

        <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <Link href="#today" className="nt-cta nt-cta--primary">
            See today&rsquo;s picks
          </Link>
          <Link href="/progress" className="nt-cta nt-cta--ghost">
            Check the record
          </Link>
        </div>

        {(live || backtest) && (
          <p className="mx-auto mt-6 max-w-[62ch] text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
            {live && (
              <>
                Live record
                {liveSince
                  ? ` since ${new Date(liveSince).toLocaleDateString("en-GB", { day: "numeric", month: "long", timeZone: "UTC" })}`
                  : ""}
                : {live.won} of {live.settled} picks won ({rate(live)})
                {live.settled < SMALL_SAMPLE ? ", still a small sample" : ""}
                .{" "}
              </>
            )}
            {backtest && (
              <>
                {live ? "Reconstructed from past matches" : "Backtest"}:{" "}
                {backtest.won.toLocaleString()} of{" "}
                {backtest.settled.toLocaleString()} ({rate(backtest)}).{" "}
              </>
            )}
            {strong && strong.record.settled > 0 && (
              <>
                Strong tips (rated {strong.minProbability}% or more):{" "}
                {strong.record.won.toLocaleString()} of{" "}
                {strong.record.settled.toLocaleString()} ({rate(strong.record)}
                ).{" "}
              </>
            )}
            <Link
              href="/progress"
              className="text-[var(--color-gold-bright)] hover:underline"
            >
              How the two differ
            </Link>
            .
          </p>
        )}
      </div>
    </section>
  );
}
