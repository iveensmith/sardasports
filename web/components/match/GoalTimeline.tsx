/**
 * The goals, in order, with a running score.
 *
 * Real events only — every row here is a `MatchEvent` synced from
 * API-Football's own event feed (see `scripts/fetch_match_stats.py`), never
 * inferred from the final score. A match with a score but no timeline
 * (fetched before events existed, or a competition the source has none for)
 * renders nothing rather than a fabricated "someone scored at some point".
 */

import type { MatchEvent } from "@/lib/types";
import { TeamCrest } from "@/components/board/TeamCrest";
import type { Badge } from "@/lib/board";

function minuteLabel(event: MatchEvent) {
  return event.added_time
    ? `${event.minute}+${event.added_time}'`
    : `${event.minute}'`;
}

export function GoalTimeline({
  events,
  home,
  away,
  homeBadge,
  awayBadge,
}: {
  events: MatchEvent[];
  home: string;
  away: string;
  homeBadge: Badge | null;
  awayBadge: Badge | null;
}) {
  if (events.length === 0) return null;

  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-6">
      <h2 className="mb-4 text-[15px] font-semibold">Goals</h2>
      <ol className="space-y-3">
        {events.map((event, index) => {
          const isHome = event.side === "home";
          return (
            <li
              key={index}
              className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-[13.5px]"
            >
              <div
                className={
                  isHome
                    ? "flex items-center justify-end gap-2 text-right"
                    : "opacity-0"
                }
              >
                {isHome && (
                  <>
                    <span>
                      <span className="font-medium">{event.player}</span>
                      {event.assist && (
                        <span className="block text-[12px] text-[var(--color-text-faint)]">
                          Assist: {event.assist}
                        </span>
                      )}
                    </span>
                    <TeamCrest badge={homeBadge} name={home} size={18} />
                  </>
                )}
              </div>

              <span
                className="inline-flex flex-col items-center rounded-[var(--radius-sm)] bg-[var(--color-surface-raised)] px-2 py-1 text-center"
                title={event.detail}
              >
                <span className="text-[11px] font-semibold tabular-nums text-[var(--color-gold-bright)]">
                  {minuteLabel(event)}
                </span>
                <span className="text-[11px] tabular-nums text-[var(--color-text-faint)]">
                  {event.home_score_after}&ndash;{event.away_score_after}
                </span>
              </span>

              <div
                className={
                  !isHome ? "flex items-center gap-2 text-left" : "opacity-0"
                }
              >
                {!isHome && (
                  <>
                    <TeamCrest badge={awayBadge} name={away} size={18} />
                    <span>
                      <span className="font-medium">{event.player}</span>
                      {event.assist && (
                        <span className="block text-[12px] text-[var(--color-text-faint)]">
                          Assist: {event.assist}
                        </span>
                      )}
                    </span>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
