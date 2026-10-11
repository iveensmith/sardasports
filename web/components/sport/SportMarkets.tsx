/**
 * Every extra market for one match: team totals, halves, quarters and the spread for
 * basketball; set betting, handicaps, first set and tiebreak for tennis.
 *
 * Rendered with a native <details>, so it opens and closes without any script and works the
 * same on a phone. Each line shows its probability, and once the match is over, what it
 * actually settled as (a tick on the side that came in), so a reader can check every line against the score.
 *
 * Priced statistically from the league's or tour's own record, and labelled so: a normal
 * distribution around an expectation, not a model trained per line.
 */

import type { SportMarket } from "@/lib/sports";

function Mark({ won }: { won: boolean | null }) {
  // Only the side that came in is marked; the other side is simply dimmed (see `Chip`).
  if (won !== true) return null;
  return (
    <span
      className="ml-1.5 text-[11px] font-semibold"
      style={{ color: "var(--color-won)" }}
    >
      <span aria-hidden>✓</span>
      <span className="sr-only"> (came in)</span>
    </span>
  );
}

function pct(value: number) {
  return `${Math.round(value)}%`;
}

function signed(line: number) {
  return line > 0 ? `+${line}` : `${line}`;
}

function Chip({
  label,
  probability,
  won,
}: {
  label: string;
  probability: number;
  won: boolean | null;
}) {
  return (
    <span
      className={`inline-flex items-baseline gap-1.5 rounded-[var(--radius-md)] border px-2 py-1 text-[12.5px] tabular-nums ${
        won === true
          ? "border-[var(--color-won)]"
          : won === false
            ? "border-[var(--color-line)] opacity-55"
            : "border-[var(--color-line)]"
      }`}
    >
      <span className="text-[var(--color-text-dim)]">{label}</span>
      <span className="font-semibold">{pct(probability)}</span>
      <Mark won={won} />
    </span>
  );
}

function Lines({ market }: { market: SportMarket }) {
  const result = market.result;
  const outcomes = (result?.lines ?? []) as string[];
  switch (market.type) {
    case "over_under":
      return (
        <div className="flex flex-wrap gap-2">
          {(market.lines ?? []).map((line, i) => (
            <span key={line.line} className="flex gap-1">
              <Chip
                label={`Over ${line.line}`}
                probability={line.prob_over}
                won={result ? outcomes[i] === "over" : null}
              />
              <Chip
                label={`Under ${line.line}`}
                probability={line.prob_under}
                won={result ? outcomes[i] === "under" : null}
              />
            </span>
          ))}
        </div>
      );
    case "handicap":
      return (
        <div className="flex flex-wrap gap-2">
          {(market.lines ?? []).map((line, i) => (
            <span key={line.line} className="flex gap-1">
              <Chip
                label={`Home ${signed(line.line)}`}
                probability={line.prob_home}
                won={result ? outcomes[i] === "home" : null}
              />
              <Chip
                label={`Away ${signed(-line.line)}`}
                probability={line.prob_away}
                won={result ? outcomes[i] === "away" : null}
              />
            </span>
          ))}
        </div>
      );
    case "three_way":
      return (
        <div className="flex flex-wrap gap-2">
          <Chip
            label="Home"
            probability={market.home ?? 0}
            won={result ? result.result === "home" : null}
          />
          <Chip
            label="Tie"
            probability={market.tie ?? 0}
            won={result ? result.result === "tie" : null}
          />
          <Chip
            label="Away"
            probability={market.away ?? 0}
            won={result ? result.result === "away" : null}
          />
        </div>
      );
    case "two_way":
      return (
        <div className="flex flex-wrap gap-2">
          <Chip
            label="Home"
            probability={market.home ?? 0}
            won={result ? result.result === "home" : null}
          />
          <Chip
            label="Away"
            probability={market.away ?? 0}
            won={result ? result.result === "away" : null}
          />
        </div>
      );
    case "yes_no":
      return (
        <div className="flex flex-wrap gap-2">
          <Chip
            label="Yes"
            probability={market.yes ?? 0}
            won={result ? result.result === "yes" : null}
          />
          <Chip
            label="No"
            probability={market.no ?? 0}
            won={result ? result.result === "no" : null}
          />
        </div>
      );
    case "correct_score": {
      const hits = (result?.scores ?? []) as number[];
      return (
        <div className="flex flex-wrap gap-2">
          {(market.scores ?? []).map((entry, i) => (
            <Chip
              key={entry.score}
              label={entry.score}
              probability={entry.prob}
              won={result ? hits[i] === 1 : null}
            />
          ))}
        </div>
      );
    }
    default:
      return null;
  }
}

export function SportMarkets({
  markets,
  homeLabel,
  awayLabel,
}: {
  markets: SportMarket[];
  homeLabel: string;
  awayLabel: string;
}) {
  if (markets.length === 0) return null;
  const groups: Array<{ name: string; items: SportMarket[] }> = [];
  for (const market of markets) {
    const existing = groups.find((g) => g.name === market.group);
    if (existing) existing.items.push(market);
    else groups.push({ name: market.group, items: [market] });
  }
  return (
    <details className="group border-t border-[var(--color-line)] bg-[var(--color-surface)]/50">
      <summary className="cursor-pointer list-none px-4 py-2 text-[12.5px] font-medium text-[var(--color-gold-bright)] hover:underline">
        All markets ({markets.length})
        <span className="ml-2 text-[var(--color-text-faint)]">
          {homeLabel} v {awayLabel}
        </span>
      </summary>
      <div className="space-y-4 px-4 pt-1 pb-4">
        {groups.map((group) => (
          <section key={group.name} aria-label={group.name}>
            <h4 className="text-[12px] font-semibold tracking-wider text-[var(--color-text-faint)] uppercase">
              {group.name}
            </h4>
            <div className="mt-2 space-y-2.5">
              {group.items.map((market) => (
                <div key={market.id}>
                  <p className="text-[13px] text-[var(--color-text-dim)]">
                    {market.name}
                    {market.expected !== undefined && market.expected !== null
                      ? ` (expected ${market.expected})`
                      : ""}
                  </p>
                  <div className="mt-1">
                    <Lines market={market} />
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
        <p className="text-[12px] leading-relaxed text-[var(--color-text-faint)]">
          Priced from the competition&rsquo;s own scoring record around this
          match&rsquo;s expectation, not by a model trained for each line. Half
          points mean no pushes; a tick marks the side of each line that came
          in.
        </p>
      </div>
    </details>
  );
}
