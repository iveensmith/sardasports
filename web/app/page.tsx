/**
 * Landing page.
 *
 * The hero is a real prediction on a real upcoming fixture, pulled live
 * from the engine. That is the most characteristic thing in this product's
 * world, and it is also the honest one: a marketing page for a prediction
 * engine that shows invented numbers would undercut the single property the
 * engine is built around.
 *
 * If the engine is unreachable or has no fixtures, the hero says so plainly
 * instead of falling back to a decorative placeholder.
 */

import Link from "next/link";
import { getBoard } from "@/lib/api";
import { competitors, isFootball, type Prediction } from "@/lib/types";
import { ProbabilitySplit } from "@/components/ProbabilitySplit";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";

export const revalidate = 300;

function HeroPrediction({ prediction }: { prediction: Prediction }) {
  const { home, away } = competitors(prediction);
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6 shadow-[0_24px_80px_-32px_rgba(0,0,0,0.9)]">
      <div className="mb-5 flex items-baseline justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate text-[17px] font-semibold">
            {home} <span className="text-[var(--color-text-faint)]">v</span>{" "}
            {away}
          </p>
          <p className="mt-1 text-[13px] text-[var(--color-text-dim)]">
            {new Date(prediction.match_date).toLocaleString(undefined, {
              weekday: "short",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        </div>
      </div>

      <ProbabilitySplit
        home={prediction.home_win}
        away={prediction.away_win}
        draw={isFootball(prediction) ? prediction.draw : undefined}
        homeLabel={home}
        awayLabel={away}
      />

      <div className="mt-6 border-t border-[var(--color-line)] pt-5">
        <ConfidenceMeter
          value={prediction.confidence}
          label={prediction.confidence_label}
        />
      </div>

      <Link
        href={`/match/${prediction.match_id}`}
        className="mt-5 inline-block text-[14px] text-[var(--color-gold-bright)] underline-offset-4 hover:underline"
      >
        See the full analysis
      </Link>
    </div>
  );
}

function HeroEmpty({ reason }: { reason: string }) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-8">
      <p className="text-[15px] font-medium">No fixture to show right now</p>
      <p className="mt-2 max-w-[46ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
        {reason}
      </p>
    </div>
  );
}

export default async function Home() {
  let hero: Prediction | null = null;
  let reason =
    "The engine only covers competitions it has trained models for, so quiet days show fewer fixtures.";

  try {
    const board = await getBoard({ view: "consensus" });
    // Lead with a fixture all three estimators agree on, most confident
    // first. A disagreement would be a poor advertisement for the engine
    // precisely because the headline number hides the split.
    hero =
      board.fixtures
        .map((f) => f.prediction)
        .filter((p): p is Prediction => p !== null)
        .sort((a, b) => b.confidence - a.confidence)[0] ?? null;
  } catch (error) {
    reason =
      error instanceof Error
        ? error.message
        : "The prediction engine could not be reached.";
  }

  return (
    <div className="mx-auto max-w-6xl px-4">
      <section className="grid items-center gap-12 py-16 md:grid-cols-[1.05fr_1fr] md:py-24">
        <div>
          <h1 className="text-balance text-[clamp(2.5rem,6vw,4.25rem)] leading-[0.98] font-bold tracking-[-0.03em]">
            Predict smarter.
            <br />
            Win with insight.
          </h1>

          <p className="mt-6 max-w-[52ch] text-[17px] leading-relaxed text-[var(--color-text-dim)]">
            AI-powered predictions across football, basketball and tennis —
            backed by 144,000 ingested matches, and honest about what the model
            does not know.
          </p>

          <div className="mt-9 flex flex-wrap gap-3">
            <Link
              href="/predictions"
              className="rounded-[var(--radius-md)] bg-[var(--color-gold)] px-5 py-3 text-[15px] font-semibold text-[#0a0806] transition-colors hover:bg-[var(--color-gold-bright)]"
            >
              Today&rsquo;s predictions
            </Link>
            <Link
              href="/analytics"
              className="rounded-[var(--radius-md)] border border-[var(--color-line-strong)] px-5 py-3 text-[15px] font-medium text-[var(--color-text)] transition-colors hover:border-[var(--color-text-faint)]"
            >
              Explore analytics
            </Link>
          </div>
        </div>

        {hero ? <HeroPrediction prediction={hero} /> : <HeroEmpty reason={reason} />}
      </section>

      {/*
        Three claims, each one a fact about the engine rather than a
        marketing adjective, and each verifiable on the site itself.
      */}
      <section className="grid gap-px overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-line)] md:grid-cols-3">
        {[
          {
            stat: "144,381",
            label: "matches ingested",
            body: "Football, basketball and tennis in one pipeline, each match used only to predict matches that came after it.",
          },
          {
            stat: "19",
            label: "trained models",
            body: "A separate model per market and per line, because ‘over 8.5 corners’ is not derivable from ‘over 9.5’.",
          },
          {
            stat: "N/A",
            label: "when it cannot price",
            body: "A market with no data reports as unavailable. The engine does not fill the gap with a number that looks real.",
          },
        ].map((item) => (
          <div key={item.label} className="bg-[var(--color-surface)] p-7">
            <p className="text-[32px] leading-none font-bold tracking-[-0.02em]">
              {item.stat}
            </p>
            <p className="mt-2 text-[13px] text-[var(--color-text-dim)]">
              {item.label}
            </p>
            <p className="mt-4 text-[14px] leading-relaxed text-[var(--color-text-dim)]">
              {item.body}
            </p>
          </div>
        ))}
      </section>
    </div>
  );
}
