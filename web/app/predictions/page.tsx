/**
 * The prediction board.
 *
 * Three views over the same card, because "what does the engine think?" has
 * three genuinely different answers worth browsing separately:
 *
 *   Consensus    — all three independent estimators back the same outcome.
 *   Disagreement — they split. The blended number sits between real
 *                  competing readings, which is the interesting case and
 *                  the one a single headline probability hides.
 *   Not called   — the engine's own confidence label is "Low", or it could
 *                  not price the fixture at all. Declining is a result, and
 *                  it gets a tab rather than being silently dropped.
 *
 * Filters are URL-driven, so a view is linkable and needs no client JS.
 * Next 16: `searchParams` is a Promise and must be awaited.
 */

import Link from "next/link";
import {
  getBoard,
  getCompetitions,
  type BoardEntry,
  type BoardView,
} from "@/lib/api";
import type { Competition } from "@/lib/types";
import { FixtureRow } from "@/components/FixtureRow";
import { pageMetadata } from "@/lib/seo";

export const revalidate = 300;

export const metadata = pageMetadata({
  title: "Prediction board",
  description:
    "The prediction board, grouped by how strongly the engine's estimators agree.",
  path: "/predictions",
  noindex: true,
});

const VIEWS: Array<{ id: BoardView; label: string; blurb: string }> = [
  {
    id: "all",
    label: "All fixtures",
    blurb: "Everything on today's card that the engine has a model for.",
  },
  {
    id: "consensus",
    label: "Strongest consensus",
    blurb:
      "All three independent estimators (Elo, Poisson and the trained model) back the same outcome. Ranked by confidence.",
  },
  {
    id: "disagreement",
    label: "Biggest disagreement",
    blurb:
      "The estimators split. The headline probability is their blend, so it sits between competing readings rather than reflecting a settled view. Most divided first.",
  },
  {
    id: "passed",
    label: "Not called",
    blurb:
      "Fixtures the engine has no coherent view of, either because its own confidence is low or because most of its estimators dissent from the blended pick. Declining to call one is a result, not a gap.",
  },
];

function ViewTabs({
  active,
  counts,
  query,
}: {
  active: BoardView;
  counts: Record<BoardView, number>;
  query: URLSearchParams;
}) {
  return (
    <div
      className="flex flex-wrap gap-1 border-b border-[var(--color-line)]"
      role="tablist"
    >
      {VIEWS.map((view) => {
        const params = new URLSearchParams(query);
        if (view.id === "all") params.delete("view");
        else params.set("view", view.id);
        const isActive = view.id === active;
        return (
          <Link
            key={view.id}
            href={`/predictions${params.toString() ? `?${params}` : ""}`}
            role="tab"
            aria-selected={isActive}
            className="-mb-px border-b-2 px-3 py-2.5 text-[14px] transition-colors"
            style={{
              borderColor: isActive ? "var(--color-gold)" : "transparent",
              color: isActive ? "var(--color-text)" : "var(--color-text-dim)",
            }}
          >
            {view.label}{" "}
            <span className="text-[var(--color-text-faint)]">
              {counts[view.id] ?? 0}
            </span>
          </Link>
        );
      })}
    </div>
  );
}

export default async function PredictionsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const first = (key: string) => {
    const value = params[key];
    return (Array.isArray(value) ? value[0] : value) ?? "";
  };

  const rawView = first("view");
  const view: BoardView = (
    ["consensus", "disagreement", "passed"].includes(rawView) ? rawView : "all"
  ) as BoardView;
  const sport = first("sport");
  const competition = first("competition");
  const minConfidence = first("min_confidence");

  let fixtures: BoardEntry[] = [];
  let counts: Record<BoardView, number> = {
    all: 0,
    consensus: 0,
    disagreement: 0,
    passed: 0,
  };
  let competitions: Competition[] = [];
  let predicted = 0;
  let error: string | null = null;

  try {
    const [board, competitionList] = await Promise.all([
      getBoard({
        view,
        sport: sport || undefined,
        competition: competition || undefined,
        minConfidence: minConfidence ? Number(minConfidence) : undefined,
      }),
      getCompetitions().catch(() => ({ competitions: [] })),
    ]);
    fixtures = board.fixtures;
    counts = board.counts;
    predicted = board.predicted;
    competitions = competitionList.competitions;
  } catch (e) {
    error = e instanceof Error ? e.message : "The engine could not be reached.";
  }

  const query = new URLSearchParams();
  if (sport) query.set("sport", sport);
  if (competition) query.set("competition", competition);
  if (minConfidence) query.set("min_confidence", minConfidence);

  const activeView = VIEWS.find((v) => v.id === view)!;

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 lg:px-10 py-12">
      <header className="mb-7">
        <h1 className="text-[32px] font-bold tracking-[-0.02em]">
          Prediction board
        </h1>
        <p className="mt-2 max-w-[66ch] text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          Every fixture the engine has a trained model for. Competitions without
          one are left out rather than predicted from an empty rating.
        </p>
      </header>

      {/* Filters first, then the views over the filtered card. */}
      <form
        className="mb-6 flex flex-wrap items-end gap-3"
        action="/predictions"
        method="get"
      >
        {view !== "all" && <input type="hidden" name="view" value={view} />}
        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] text-[var(--color-text-faint)]">
            Sport
          </span>
          <select
            name="sport"
            defaultValue={sport}
            className="min-w-[9rem] rounded-[var(--radius-md)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] px-3 py-2 text-[14px]"
          >
            <option value="">All sports</option>
            <option value="football">Football</option>
            <option value="basketball">Basketball</option>
            <option value="tennis">Tennis</option>
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] text-[var(--color-text-faint)]">
            Competition
          </span>
          <select
            name="competition"
            defaultValue={competition}
            className="min-w-[15rem] rounded-[var(--radius-md)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] px-3 py-2 text-[14px]"
          >
            <option value="">All competitions</option>
            {competitions.map((c) => (
              <option key={`${c.sport}-${c.competition}`} value={c.competition}>
                {c.competition}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] text-[var(--color-text-faint)]">
            Minimum confidence
          </span>
          <input
            type="number"
            name="min_confidence"
            min={0}
            max={100}
            step={5}
            defaultValue={minConfidence}
            placeholder="Any"
            className="w-[9rem] rounded-[var(--radius-md)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] px-3 py-2 text-[14px]"
          />
        </label>

        <button
          type="submit"
          className="rounded-[var(--radius-md)] border border-[var(--color-line-strong)] px-4 py-2 text-[14px] font-medium transition-colors hover:border-[var(--color-text-faint)]"
        >
          Apply filters
        </button>
      </form>

      {error ? (
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[15px] font-medium">The engine is unreachable</p>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">
            {error}
          </p>
        </div>
      ) : (
        <>
          <ViewTabs active={view} counts={counts} query={query} />

          <p className="mt-4 mb-4 max-w-[70ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
            {activeView.blurb}
          </p>

          {fixtures.length === 0 ? (
            <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-8">
              <p className="text-[15px] font-medium">
                {view === "all"
                  ? "No fixtures today"
                  : "Nothing in this view right now"}
              </p>
              <p className="mt-2 max-w-[54ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
                {view === "all" ? (
                  <>
                    Run{" "}
                    <code className="text-[var(--color-text)]">
                      scripts/fetch_upcoming_fixtures.py
                    </code>{" "}
                    to ingest the next few days, then reload.
                  </>
                ) : (
                  "Try another view, or widen the filters above."
                )}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex items-baseline justify-between px-1 pb-1 text-[13px] text-[var(--color-text-dim)]">
                <span>
                  {fixtures.length} fixture{fixtures.length === 1 ? "" : "s"}
                </span>
                <span className="text-[var(--color-text-faint)]">
                  {predicted === fixtures.length
                    ? "Sorted by kick-off"
                    : `${predicted} priced`}
                </span>
              </div>
              {fixtures.map((fixture) => (
                <FixtureRow key={fixture.match_id} fixture={fixture} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
