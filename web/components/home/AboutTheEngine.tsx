/**
 * The case for the engine, in prose, with its real counts beside it.
 *
 * The reference site fills this slot with user reviews, partner logos and a
 * company video. This site has none of those, and inventing them would be the
 * opposite of its argument, so the slot carries the one thing that is real:
 * what the engine does, and how much of it has been checked.
 *
 * Every figure is a prop, never a guess. A count of zero shows as a dash.
 * There is deliberately no win-rate tile here: live and reconstructed picks are
 * different kinds of evidence, the hero states each on its own, and a single
 * blended percentage would hide the distinction the track record exists to keep.
 */

import Link from "next/link";

function Tile({
  label,
  value,
}: {
  label: string;
  value: string | number | null;
}) {
  // Label above, number below, pushed apart: the tiles stretch to the height of
  // the text beside them, and a number floating at the top of a tall box looks
  // unfinished where one at the foot reads as anchored.
  return (
    <div className="flex min-h-[88px] flex-col justify-between rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] px-5 py-4">
      <p className="text-[12.5px] text-[var(--color-text-faint)]">{label}</p>
      <p className="mt-3 text-[32px] leading-none font-bold tabular-nums">
        {value ?? "—"}
      </p>
    </div>
  );
}

export function AboutTheEngine({
  gradedPicks,
  livePicks,
  competitionCount,
  countryCount,
  firstSettledDate,
}: {
  gradedPicks: number;
  livePicks: number;
  competitionCount: number | null;
  countryCount: number | null;
  firstSettledDate: string | null;
}) {
  const since = firstSettledDate
    ? new Date(firstSettledDate).toLocaleDateString("en-GB", {
        month: "long",
        year: "numeric",
        timeZone: "UTC",
      })
    : null;
  const mostlyReconstructed = livePicks < gradedPicks / 2;

  return (
    <section>
      <div className="grid gap-8 md:grid-cols-[1.1fr_1fr] md:items-stretch">
        <div>
          <h2 className="text-[clamp(1.5rem,3vw,1.9rem)] font-bold tracking-[-0.02em]">
            Built to be checked, not just believed
          </h2>
          <p className="mt-3 max-w-[62ch] text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
            Every pick on this site comes from one calibrated engine, not from a
            person typing in tips. It blends three independent estimators, an
            Elo rating system, a Poisson goal model and a gradient-boosted
            classifier trained for each market, into a single probability. Each
            pick is then graded against the real final score
            {since ? `, going back to ${since}` : ""}.
          </p>
          <p className="mt-3 max-w-[62ch] text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
            {mostlyReconstructed
              ? "Most of that record is reconstructed: each prediction was generated after the match from history cut off at kick-off, so it could not have seen the result, but it was never at risk of being wrong in public. The live record, stored before kick-off, grows as the board runs forward, and the two are always reported separately."
              : "The record combines picks stored before kick-off with picks reconstructed afterwards from history cut off at kick-off. The two are always reported separately, because they are not the same kind of evidence."}
          </p>
          <p className="mt-3 max-w-[62ch] text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
            A losing pick stays on the record. The full history, wins and losses
            both, is on the{" "}
            <Link
              href="/progress"
              className="text-[var(--color-gold-bright)] hover:underline"
            >
              track record page
            </Link>
            , and you can download it.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3 md:grid-rows-2">
          <Tile
            label="Graded picks"
            value={gradedPicks > 0 ? gradedPicks.toLocaleString() : null}
          />
          <Tile
            label="Of which live"
            value={livePicks > 0 ? livePicks.toLocaleString() : null}
          />
          <Tile label="Competitions" value={competitionCount} />
          <Tile label="Countries" value={countryCount} />
        </div>
      </div>
    </section>
  );
}
