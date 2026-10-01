/**
 * The narrative the reference site tells with a decade of Trustpilot
 * reviews, a partner-logo strip, and a YouTube explainer — none of which
 * this site has a real one of. Reviews, "trusted by" logos and a company
 * video would all have to be invented to fill the same slot, so this
 * replaces them with the one thing that isn't invented: the engine's own
 * real numbers, restated as prose instead of left to the board tables to
 * imply.
 *
 * Every figure here is a prop, not a guess — if `settled` is 0 (a fresh
 * deployment, or the engine unreachable), the stat tiles show "—" rather
 * than a fabricated number, the same rule the board itself follows.
 */

function Tile({
  label,
  value,
}: {
  label: string;
  value: string | number | null;
}) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] px-4 py-3">
      <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
        {label}
      </p>
      <p className="mt-1 text-[26px] leading-none font-bold tabular-nums">
        {value ?? "—"}
      </p>
    </div>
  );
}

export function AboutTheEngine({
  settled,
  winRate,
  isBacktest,
  competitionCount,
  countryCount,
  firstSettledDate,
}: {
  settled: number;
  winRate: string | null;
  isBacktest: boolean;
  competitionCount: number | null;
  countryCount: number | null;
  firstSettledDate: string | null;
}) {
  const since = firstSettledDate
    ? new Date(firstSettledDate).toLocaleDateString(undefined, {
        month: "long",
        year: "numeric",
      })
    : null;

  return (
    <section className="mt-16">
      <div className="grid gap-8 md:grid-cols-[1.1fr_1fr] md:items-start">
        <div>
          <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
            About the engine
          </p>
          <h2 className="mt-2.5 text-[clamp(1.5rem,3vw,1.9rem)] font-bold tracking-[-0.02em]">
            Built to be graded, not just believed
          </h2>
          <p className="mt-3 max-w-[62ch] text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
            Every pick above comes from the same calibrated engine, not a person
            typing in tips. It blends three independent estimators &mdash; an
            Elo rating system, a Poisson goal model, and a gradient-boosted
            classifier trained per market &mdash; into one probability, then
            settles every call against the real final score
            {since ? `, going back to ${since}` : ""}.
          </p>
          <p className="mt-3 max-w-[62ch] text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
            {isBacktest
              ? "The record below is currently a backtest — generated after each match from history truncated at kick-off, so it can't have leaked the result, but it hasn't been risked live yet either. The live record starts filling in on its own as the board runs forward, and is always labelled separately from this one."
              : "Nothing here is edited by hand after the fact: a losing pick stays on the record exactly as it was called, and the full history — wins and losses both — is public on the track record page."}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Tile label="Settled calls" value={settled > 0 ? settled : null} />
          <Tile label="Win rate" value={winRate} />
          <Tile label="Competitions" value={competitionCount} />
          <Tile label="Countries" value={countryCount} />
        </div>
      </div>
    </section>
  );
}
