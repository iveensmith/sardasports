/**
 * Model leaderboard.
 *
 * Ranked by edge over baseline rather than by accuracy, because accuracy
 * across different markets is not comparable: a line that falls one way 78%
 * of the time hands a model 78% for learning nothing. Each trainer records
 * the benchmark its own market has to beat, and the gap is the ranking.
 *
 * Small samples are flagged rather than hidden, and sort behind a real
 * sample at equal standing — a model evaluated on a few hundred matches can
 * top a table on noise alone.
 */

import { getLeaderboard, type LeaderboardRow, type LeaderboardSort } from "@/lib/api";

export const revalidate = 600;

export const metadata = {
  title: "Model leaderboard — UniquePredict",
};

const SORTS: Array<{ id: LeaderboardSort; label: string }> = [
  { id: "edge", label: "Edge over baseline" },
  { id: "accuracy", label: "Accuracy" },
  { id: "log_loss", label: "Log loss" },
  { id: "samples", label: "Sample size" },
];

const SPORTS = ["football", "basketball", "tennis"] as const;

const SPORT_COLOR: Record<string, string> = {
  football: "var(--color-home)",
  basketball: "var(--color-draw)",
  tennis: "var(--color-away)",
};

function EdgeCell({ row }: { row: LeaderboardRow }) {
  if (row.edge === null) {
    return (
      <span
        className="text-[13px]"
        style={{ color: "var(--color-unknown)" }}
        title="This model records no baseline, so its accuracy alone does not say how much is skill."
      >
        no baseline
      </span>
    );
  }
  const positive = row.edge > 0;
  return (
    <span
      className="font-semibold"
      style={{
        color: positive ? "var(--color-gold-bright)" : "var(--color-text-dim)",
      }}
    >
      {positive ? "+" : ""}
      {row.edge.toFixed(2)}
    </span>
  );
}

function TrendCell({ trend }: { trend: number | null }) {
  if (trend === null) {
    return (
      <span
        className="text-[13px]"
        style={{ color: "var(--color-text-faint)" }}
        title="No earlier version of this model to compare against."
      >
        —
      </span>
    );
  }
  // Arrow plus sign, never colour alone.
  const up = trend > 0;
  const flat = Math.abs(trend) < 0.005;
  return (
    <span className="text-[13px] text-[var(--color-text-dim)]">
      {flat ? "unchanged" : `${up ? "▲" : "▼"} ${Math.abs(trend).toFixed(2)}`}
    </span>
  );
}

export default async function LeaderboardPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const first = (key: string) => {
    const value = params[key];
    return (Array.isArray(value) ? value[0] : value) ?? "";
  };

  const rawSort = first("sort");
  const sort: LeaderboardSort = (
    SORTS.some((s) => s.id === rawSort) ? rawSort : "edge"
  ) as LeaderboardSort;
  const sport = first("sport");

  let rows: LeaderboardRow[] = [];
  let summary = { with_baseline: 0, beating_baseline: 0, provisional: 0 };
  let threshold = 1000;
  let error: string | null = null;

  try {
    const board = await getLeaderboard({ sort, sport: sport || undefined });
    rows = board.models;
    summary = board.summary;
    threshold = board.provisional_threshold;
  } catch (e) {
    error = e instanceof Error ? e.message : "The engine could not be reached.";
  }

  const linkFor = (next: Partial<{ sort: string; sport: string }>) => {
    const query = new URLSearchParams();
    const nextSort = next.sort ?? sort;
    const nextSport = next.sport ?? sport;
    if (nextSort !== "edge") query.set("sort", nextSort);
    if (nextSport) query.set("sport", nextSport);
    return `/leaderboard${query.toString() ? `?${query}` : ""}`;
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <header className="mb-7">
        <h1 className="text-[32px] font-bold tracking-[-0.02em]">
          Model leaderboard
        </h1>
        <p className="mt-2 max-w-[70ch] text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          Every trained model, ranked by how far it beats the benchmark its own
          market has to clear. Accuracy across different markets is not
          comparable — a line that falls one way most of the time hands a model
          a high score for learning very little — so the gap is what ranks here.
        </p>
      </header>

      {error ? (
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[15px] font-medium">The engine is unreachable</p>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">{error}</p>
        </div>
      ) : (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-x-6 gap-y-2 text-[13px] text-[var(--color-text-dim)]">
            <span>
              <strong className="text-[var(--color-text)]">
                {summary.beating_baseline}
              </strong>{" "}
              of {summary.with_baseline} beat their baseline by more than a
              point
            </span>
            {summary.provisional > 0 && (
              <span>
                <strong className="text-[var(--color-text)]">
                  {summary.provisional}
                </strong>{" "}
                on a provisional sample (under {threshold.toLocaleString()}{" "}
                matches)
              </span>
            )}
          </div>

          <div className="mb-5 flex flex-wrap gap-4">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-[12px] text-[var(--color-text-faint)]">
                Sort by
              </span>
              {SORTS.map((option) => (
                <a
                  key={option.id}
                  href={linkFor({ sort: option.id })}
                  className="rounded-full border px-3 py-1 text-[13px] transition-colors"
                  style={{
                    borderColor:
                      option.id === sort
                        ? "var(--color-gold-dim)"
                        : "var(--color-line-strong)",
                    color:
                      option.id === sort
                        ? "var(--color-gold-bright)"
                        : "var(--color-text-dim)",
                  }}
                >
                  {option.label}
                </a>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-[12px] text-[var(--color-text-faint)]">
                Sport
              </span>
              {["", ...SPORTS].map((option) => (
                <a
                  key={option || "all"}
                  href={linkFor({ sport: option })}
                  className="rounded-full border px-3 py-1 text-[13px] capitalize transition-colors"
                  style={{
                    borderColor:
                      option === sport
                        ? "var(--color-gold-dim)"
                        : "var(--color-line-strong)",
                    color:
                      option === sport
                        ? "var(--color-gold-bright)"
                        : "var(--color-text-dim)",
                  }}
                >
                  {option || "All"}
                </a>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)]">
            <table className="w-full min-w-[54rem] text-[14px]">
              <caption className="sr-only">
                Models ranked by edge over their market baseline
              </caption>
              <thead>
                <tr className="text-left text-[12px] text-[var(--color-text-faint)]">
                  <th className="px-4 py-3 font-medium">#</th>
                  <th className="px-4 py-3 font-medium">Model</th>
                  <th className="px-4 py-3 text-right font-medium">Edge</th>
                  <th className="px-4 py-3 text-right font-medium">Accuracy</th>
                  <th className="px-4 py-3 text-right font-medium">Baseline</th>
                  <th className="px-4 py-3 text-right font-medium">Log loss</th>
                  <th className="px-4 py-3 text-right font-medium">Sample</th>
                  <th className="px-4 py-3 text-right font-medium">
                    Since last train
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.model_name}
                    className="border-t border-[var(--color-line)]/70"
                  >
                    <td className="px-4 py-3 text-[var(--color-text-faint)]">
                      {row.rank}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <span
                          aria-hidden
                          className="inline-block h-2 w-2 shrink-0 rounded-full"
                          style={{
                            background:
                              SPORT_COLOR[row.sport] ?? "var(--color-unknown)",
                          }}
                        />
                        <span className="font-medium">{row.label}</span>
                        {row.provisional && (
                          <span
                            className="rounded border px-1.5 py-0.5 text-[10px] tracking-wide uppercase"
                            style={{
                              borderColor: "var(--color-away)",
                              color: "var(--color-away)",
                            }}
                            title={`Evaluated on fewer than ${threshold.toLocaleString()} matches — treat the edge as provisional.`}
                          >
                            provisional
                          </span>
                        )}
                      </div>
                      <p className="mt-0.5 pl-[1.25rem] text-[12px] text-[var(--color-text-faint)]">
                        {row.sport} · {row.market}
                        {row.baseline_kind ? ` · ${row.baseline_kind}` : ""}
                      </p>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <EdgeCell row={row} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      {row.accuracy.toFixed(2)}%
                    </td>
                    <td className="px-4 py-3 text-right text-[var(--color-text-dim)]">
                      {row.baseline === null
                        ? "—"
                        : `${row.baseline.toFixed(2)}%`}
                    </td>
                    <td className="px-4 py-3 text-right text-[var(--color-text-dim)]">
                      {row.log_loss === null ? "—" : row.log_loss.toFixed(4)}
                    </td>
                    <td className="px-4 py-3 text-right text-[var(--color-text-dim)]">
                      {row.samples === null
                        ? "—"
                        : row.samples.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <TrendCell trend={row.trend} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="mt-4 max-w-[74ch] text-[13px] leading-relaxed text-[var(--color-text-faint)]">
            Edge is accuracy minus the baseline, in percentage points, measured
            on the held-out test period each model was evaluated against — never
            on data it trained on. A model with no recorded baseline shows its
            accuracy but no edge, because there is nothing to say how much of
            that accuracy is skill.
          </p>
        </>
      )}
    </div>
  );
}
