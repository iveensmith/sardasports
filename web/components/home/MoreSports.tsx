/**
 * "Basketball and tennis too": the way into the other two sports from the home page.
 *
 * Football is the daily board above. The other two have their own pages, and this
 * is where a visitor to the home page learns they exist. The figures on each card
 * come from the engine (how many finished matches are on record and how recent the
 * newest is), so the card says the same thing the page behind it does: when there
 * are no upcoming fixtures it says so, and it never presents old data as current.
 */

import Link from "next/link";
import { SportMark } from "@/components/sport/SportMark";
import { SPORT_COPY } from "@/lib/sportContent";
import {
  ageLabel,
  shortDate,
  type OtherSportKey,
  type SportSummary,
} from "@/lib/sports";

const SPORTS: OtherSportKey[] = ["basketball", "tennis"];

function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  const then = Date.parse(iso.slice(0, 10));
  return Number.isNaN(then)
    ? null
    : Math.max(0, Math.floor((Date.now() - then) / 86_400_000));
}

export function MoreSports({ sports }: { sports: SportSummary[] | null }) {
  return (
    <section aria-labelledby="more-sports-heading">
      <div className="max-w-[72ch]">
        <h2
          id="more-sports-heading"
          className="text-[clamp(1.5rem,3vw,1.9rem)] font-bold tracking-[-0.02em]"
        >
          Basketball and tennis predictions too
        </h2>
        <p className="mt-3 text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
          The same engine prices NBA games and ATP and WTA matches. Football has
          the daily board and the public record; these two have their own pages,
          where each model is shown beside the simple rule it has to beat.
        </p>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        {SPORTS.map((key) => {
          const copy = SPORT_COPY[key];
          const summary = sports?.find((s) => s.sport === key) ?? null;
          const age = daysSince(summary?.last_result_date ?? null);
          return (
            <Link
              key={key}
              href={copy.path}
              className="group flex flex-col rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5 transition-colors hover:border-[var(--color-line-strong)]"
            >
              <span className="flex items-center gap-3">
                <SportMark sport={key} size={28} />
                <span className="text-[18px] font-bold tracking-[-0.015em]">
                  {key === "tennis" ? "Tennis" : "Basketball"} predictions
                </span>
              </span>
              <span className="mt-3 text-[14px] text-[var(--color-text)]">
                {copy.cardLine}
              </span>
              {summary && (
                <span className="mt-2 text-[13px] leading-relaxed text-[var(--color-text-dim)]">
                  {summary.matches_on_record.toLocaleString("en-GB")} finished
                  matches on record, the newest on{" "}
                  {shortDate(summary.last_result_date)}
                  {age !== null && age > 14
                    ? ` (${ageLabel(age)} ago)`
                    : ""}.{" "}
                  {summary.upcoming_fixtures > 0
                    ? `${summary.upcoming_fixtures} upcoming with predictions.`
                    : "No upcoming predictions yet."}
                </span>
              )}
              <span className="mt-4 text-[13px] font-medium text-[var(--color-gold-bright)] underline-offset-4 group-hover:underline">
                See {key} predictions
              </span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
