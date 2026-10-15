/**
 * The landing banner: the wordmark and the claim on the left, the drawn sports
 * picture on the right, the two ways in beneath.
 *
 * It is always dark, even when the reader has chosen the light theme: it is the
 * brand's banner, black with yellow, and a pale version of it would be a different
 * brand. `data-theme="dark"` on the section re-points the colour tokens for
 * everything inside it (see the attribute rule in globals.css), so nothing here is
 * hard-coded to a colour.
 *
 * **The H1 is the search phrase, not the logo.** "SARDASPORTS" is drawn big and is
 * what the eye reads first, but the heading's text is "SARDASPORTS: football
 * predictions, every one graded", as the page's main heading has been since the
 * rebuild. The big letters are decorative and hidden from assistive technology so
 * the heading is not read twice.
 */

import Link from "next/link";
import { HeroArt, HeroBokeh } from "@/components/home/HeroArt";
import { ArrowRight, Trophy } from "@/components/home/icons";

export function HomeHero({ fixturesToday }: { fixturesToday: number }) {
  return (
    <section
      data-theme="dark"
      className="relative isolate overflow-hidden border-b border-[var(--color-line)] bg-[var(--color-base)] text-[var(--color-text)]"
    >
      {/* Light and colour, behind everything: a floodlight top-left, warmth where
          the picture is, and a hint of pitch along the foot. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-20"
        style={{
          background: [
            "radial-gradient(46% 80% at 10% -10%, rgba(255,255,255,0.13), transparent 70%)",
            "radial-gradient(54% 90% at 80% 45%, rgba(245,192,0,0.17), transparent 68%)",
            "linear-gradient(0deg, rgba(25,158,112,0.16), transparent 38%)",
            "linear-gradient(180deg, #0b111a 0%, #06090f 100%)",
          ].join(", "),
        }}
      />
      <HeroBokeh className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-28 w-full" />

      <div className="mx-auto grid w-full max-w-[1200px] items-center gap-4 px-4 py-10 sm:px-6 lg:min-h-[470px] lg:grid-cols-[1.02fr_0.98fr] lg:gap-6 lg:px-10 lg:py-12">
        <div>
          <p className="text-[14px] font-semibold tracking-[0.3em] text-[var(--color-gold)] uppercase sm:text-[17px]">
            Welcome to
          </p>

          <h1 className="mt-2">
            <span className="sr-only">
              SARDASPORTS: football predictions, every one graded
            </span>
            <span
              aria-hidden
              className="block origin-left -skew-x-[8deg] font-black tracking-[-0.035em] text-[clamp(2.4rem,9.2vw,5.5rem)] leading-[0.92] whitespace-nowrap"
            >
              <span className="text-white">SARDA</span>
              <span className="text-[var(--color-gold)]">SPORTS</span>
            </span>
          </h1>

          <div className="mt-4 flex items-center gap-3 sm:gap-4">
            <span aria-hidden className="h-[3px] w-8 shrink-0 rounded-full bg-[var(--color-gold)] sm:w-12" />
            <p className="text-[12px] font-semibold tracking-[0.42em] text-white uppercase sm:text-[15px]">
              Sport predictions
            </p>
            <span aria-hidden className="h-[3px] w-8 shrink-0 rounded-full bg-[var(--color-gold)] sm:w-12" />
          </div>

          <p className="mt-6 max-w-[50ch] text-[15.5px] leading-relaxed text-white/90 sm:text-[16.5px]">
            <b className="font-bold text-white">
              Calibrated predictions. In-depth numbers. Every pick graded in
              public.
            </b>{" "}
            The best AI prediction site for football: free predictions and tips
            from a calibrated engine
            {fixturesToday > 0 ? (
              <>
                , with{" "}
                <b className="font-bold text-white">{fixturesToday}</b>{" "}
                {fixturesToday === 1 ? "fixture" : "fixtures"} on today&rsquo;s
                board
              </>
            ) : null}
            . Basketball and tennis too. Create a free account to unlock premium
            and keep your preferences.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            {/* A plain anchor, not <Link>: the router treats a second click on the
                address it is already at as "nothing to do", so after the page had
                been scrolled back up the button did nothing. */}
            <a href="#today" className="nt-cta nt-cta--primary">
              View today&rsquo;s predictions
              <ArrowRight size={18} />
            </a>
            <Link href="/progress" className="nt-cta nt-cta--ghost">
              <Trophy size={18} />
              Check the record
            </Link>
            <Link
              href="/signup"
              className="px-1 text-[13.5px] font-bold text-white underline decoration-[var(--color-gold)] decoration-2 underline-offset-[6px] transition-colors hover:text-[var(--color-gold-bright)]"
            >
              Create a free account
            </Link>
          </div>
        </div>

        <div className="relative mx-auto w-full max-w-[560px] lg:max-w-none">
          <HeroArt className="h-auto w-full" />
          <p
            aria-hidden
            className="pointer-events-none absolute right-0 bottom-3 hidden -rotate-[8deg] text-right text-[clamp(0.9rem,1.9vw,1.4rem)] leading-[1.1] font-black tracking-[-0.01em] text-white italic sm:block"
          >
            Predict smart.
            <br />
            Check every pick.
            <br />
            <span className="text-[var(--color-gold)]">Pick with SARDASPORTS.</span>
            <span className="mt-1.5 ml-auto block h-[4px] w-[78%] -skew-x-[28deg] rounded-sm bg-[var(--color-gold)]" />
          </p>
        </div>
      </div>
    </section>
  );
}
