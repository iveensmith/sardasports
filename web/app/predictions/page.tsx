/**
 * Today's Predictions.
 *
 * A dense list, not a grid of identical cards. The content here is
 * comparative — people scan for the strongest call of the day — and a card
 * grid forces the eye to re-anchor on every tile. A table-like row puts the
 * probability split in the same horizontal position every time, which is
 * what makes scanning possible.
 */

import Link from "next/link";
import { getBoard, type BoardEntry } from "@/lib/api";
import { competitors, isFootball, type Prediction } from "@/lib/types";
import { ProbabilitySplit } from "@/components/ProbabilitySplit";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";

export const revalidate = 300;

export const metadata = {
  title: "Today's predictions — UniquePredict",
};

function Row({ fixture }: { fixture: BoardEntry }) {
  const prediction = fixture.prediction;
  const names = prediction
    ? competitors(prediction)
    : { home: fixture.home_team, away: fixture.away_team };

  const kickoff = new Date(fixture.match_date).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <Link
      href={`/match/${fixture.match_id}`}
      className="grid grid-cols-[auto_1fr] items-center gap-x-5 gap-y-3 border-t border-[var(--color-line)] px-4 py-4 transition-colors hover:bg-[var(--color-surface-raised)] md:grid-cols-[4.5rem_minmax(0,1fr)_minmax(0,18rem)_auto]"
    >
      <div className="text-[13px] text-[var(--color-text-dim)]">{kickoff}</div>

      <div className="min-w-0">
        <p className="truncate text-[15px] font-medium">
          {names.home} <span className="text-[var(--color-text-faint)]">v</span>{" "}
          {names.away}
        </p>
        <p className="mt-0.5 truncate text-[12px] text-[var(--color-text-faint)]">
          {fixture.competition}
        </p>
      </div>

      <div className="col-span-2 md:col-span-1">
        {prediction ? (
          <ProbabilitySplit
            compact
            home={prediction.home_win}
            away={prediction.away_win}
            draw={isFootball(prediction) ? prediction.draw : undefined}
            homeLabel={names.home}
            awayLabel={names.away}
          />
        ) : (
          <p className="text-[13px] text-[var(--color-text-faint)]">
            Prediction unavailable
          </p>
        )}
      </div>

      <div className="justify-self-start md:justify-self-end">
        {prediction && (
          <ConfidenceMeter
            variant="pill"
            value={prediction.confidence}
            label={prediction.confidence_label}
          />
        )}
      </div>
    </Link>
  );
}

export default async function PredictionsPage() {
  let fixtures: BoardEntry[] = [];
  let predicted = 0;
  let error: string | null = null;

  try {
    const board = await getBoard();
    fixtures = board.fixtures;
    predicted = board.predicted;
  } catch (e) {
    error = e instanceof Error ? e.message : "The engine could not be reached.";
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <header className="mb-8">
        <h1 className="text-[32px] font-bold tracking-[-0.02em]">
          Today&rsquo;s predictions
        </h1>
        <p className="mt-2 max-w-[62ch] text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          Every fixture the engine has a trained model for. Competitions
          without one are left out rather than predicted from an empty rating.
        </p>
      </header>

      {error ? (
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[15px] font-medium">The engine is unreachable</p>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">{error}</p>
        </div>
      ) : fixtures.length === 0 ? (
        <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-8">
          <p className="text-[15px] font-medium">No fixtures today</p>
          <p className="mt-2 max-w-[52ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
            Run{" "}
            <code className="text-[var(--color-text)]">
              scripts/fetch_upcoming_fixtures.py
            </code>{" "}
            to ingest the next few days of fixtures, then reload.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)]">
          <div className="flex items-baseline justify-between px-4 py-3 text-[13px] text-[var(--color-text-dim)]">
            <span>
              {fixtures.length} fixture{fixtures.length === 1 ? "" : "s"}
            </span>
            <span className="text-[var(--color-text-faint)]">
              {predicted === fixtures.length
                ? "Sorted by kick-off"
                : `${predicted} priced · sorted by kick-off`}
            </span>
          </div>
          {fixtures.map((fixture) => (
            <Row key={fixture.match_id} fixture={fixture} />
          ))}
        </div>
      )}
    </div>
  );
}
