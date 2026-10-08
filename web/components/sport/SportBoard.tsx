/**
 * One day's basketball or tennis matches, grouped by competition, each with its
 * prediction.
 *
 * Every row says where its prediction came from, because that decides how much it
 * proves: "Stored in advance" was written before the match and counts towards the
 * record; "Calculated now" is what the engine says today about a match that may
 * already be over, shown for illustration and never counted as a pick that was
 * published. A day with nothing on it says so, rather than showing an empty table.
 */

import Link from "next/link";
import { CountryMark } from "@/components/board/CountryMark";
import { matchPath } from "@/lib/seo";
import {
  ageLabel,
  kickoffTime,
  shortDate,
  type OtherSportKey,
  type SportBoard as Board,
  type SportBoardCompetition,
  type SportBoardMatch,
} from "@/lib/sports";

const SOURCE_NOTE: Record<SportBoardMatch["source"], string> = {
  stored: "Stored in advance",
  reconstructed: "Stored after the start",
  calculated: "Calculated now",
  unpriced: "Not enough history",
};

function dayLabel(offset: number, iso: string): string {
  if (offset === 0) return "Today";
  if (offset === -1) return "Yesterday";
  if (offset === 1) return "Tomorrow";
  return shortDate(iso).slice(0, -5);
}

function isoPlus(base: string, days: number): string {
  const date = new Date(`${base}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function SportDayStrip({
  sport,
  active,
  today,
}: {
  sport: OtherSportKey;
  active: string;
  today: string;
}) {
  const offsets = [-2, -1, 0, 1, 2, 3];
  return (
    <nav
      aria-label="Choose a day"
      className="flex flex-wrap items-center gap-1"
    >
      {offsets.map((offset) => {
        const day = isoPlus(today, offset);
        const isActive = day === active;
        return (
          <Link
            key={day}
            prefetch={false}
            href={offset === 0 ? `/${sport}` : `/${sport}?date=${day}`}
            aria-current={isActive ? "date" : undefined}
            className={`rounded-[var(--radius-md)] px-3 py-1.5 text-[13px] transition-colors ${
              isActive
                ? "bg-[var(--color-gold)] font-semibold text-[var(--color-ink-on-accent)]"
                : "text-[var(--color-text-dim)] hover:text-[var(--color-text)]"
            }`}
          >
            {dayLabel(offset, day)}
          </Link>
        );
      })}
    </nav>
  );
}

function WinBar({ match }: { match: SportBoardMatch }) {
  if (match.home_win === null || match.away_win === null) {
    return <span className="text-[var(--color-text-faint)]">–</span>;
  }
  const home = Math.round(match.home_win);
  return (
    <div className="w-[132px]">
      <div
        className="flex h-1.5 overflow-hidden rounded-full"
        role="img"
        aria-label={`${match.home} ${home}%, ${match.away} ${100 - home}%`}
      >
        <span
          style={{ width: `${home}%`, background: "var(--color-home)" }}
          aria-hidden
        />
        <span
          style={{ width: `${100 - home}%`, background: "var(--color-away)" }}
          aria-hidden
        />
      </div>
      <div className="mt-1 flex justify-between text-[12px] tabular-nums text-[var(--color-text-dim)]">
        <span>{home}%</span>
        <span>{100 - home}%</span>
      </div>
    </div>
  );
}

function Row({
  match,
  sport,
}: {
  match: SportBoardMatch;
  sport: OtherSportKey;
}) {
  const done = match.status === "completed";
  const totalUnit = sport === "tennis" ? "games" : "pts";
  const actualTotal =
    sport === "tennis"
      ? match.home_games !== null && match.away_games !== null
        ? match.home_games + match.away_games
        : null
      : match.home_score !== null && match.away_score !== null
        ? match.home_score + match.away_score
        : null;

  return (
    <tr className="border-t border-[var(--color-line)] align-top">
      <td className="px-4 py-3 whitespace-nowrap text-[13px] tabular-nums text-[var(--color-text-dim)]">
        {kickoffTime(match.kickoff)}
      </td>
      <td className="px-4 py-3">
        <Link
          href={matchPath(match.home, match.away, match.match_id)}
          className="font-medium hover:text-[var(--color-gold-bright)]"
        >
          {match.home} <span className="text-[var(--color-text-faint)]">v</span>{" "}
          {match.away}
        </Link>
        {match.surface && (
          <span className="block text-[12px] text-[var(--color-text-faint)]">
            {match.surface.toLowerCase()}
          </span>
        )}
      </td>
      <td className="px-4 py-3">
        <WinBar match={match} />
      </td>
      <td className="px-4 py-3">
        {match.pick ? (
          <>
            <span className="font-medium">{match.pick.name}</span>{" "}
            <span className="tabular-nums text-[var(--color-text-dim)]">
              {match.pick.probability.toFixed(0)}%
            </span>
            <span className="block text-[12px] text-[var(--color-text-faint)]">
              {SOURCE_NOTE[match.source]}
              {match.ratings_age_days
                ? `, ratings ${ageLabel(match.ratings_age_days)} old`
                : ""}
            </span>
          </>
        ) : (
          <span className="text-[var(--color-text-faint)]">
            {SOURCE_NOTE.unpriced}
          </span>
        )}
      </td>
      <td className="px-4 py-3 whitespace-nowrap">
        {match.total ? (
          <>
            <span className="tabular-nums">
              {match.total.prob_over >= 50 ? "Over" : "Under"}{" "}
              {match.total.line}
            </span>
            <span className="block text-[12px] tabular-nums text-[var(--color-text-dim)]">
              {Math.round(
                match.total.prob_over >= 50
                  ? match.total.prob_over
                  : 100 - match.total.prob_over,
              )}
              %
              {done && actualTotal !== null
                ? `, was ${actualTotal} ${totalUnit}`
                : ""}
            </span>
          </>
        ) : (
          <span className="text-[var(--color-text-faint)]">–</span>
        )}
      </td>
      <td className="px-4 py-3 whitespace-nowrap">
        {done ? (
          <>
            <span className="tabular-nums">
              {match.home_score}–{match.away_score}
            </span>
            {match.winner_correct !== null && (
              <span
                className={`ml-2 text-[12.5px] font-medium ${
                  match.winner_correct
                    ? "text-[var(--color-won)]"
                    : "text-[var(--color-lost)]"
                }`}
              >
                {match.winner_correct ? "Right" : "Wrong"}
              </span>
            )}
          </>
        ) : (
          <span className="text-[var(--color-text-faint)]">
            {match.in_play ? "In play" : "Upcoming"}
          </span>
        )}
      </td>
    </tr>
  );
}

function Group({
  group,
  sport,
}: {
  group: SportBoardCompetition;
  sport: OtherSportKey;
}) {
  return (
    <section
      aria-label={group.name}
      className="overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)]"
    >
      <header className="flex items-center gap-2.5 border-b border-[var(--color-line)] px-4 py-3">
        {sport === "basketball" && <CountryMark code={group.country_code} />}
        <h3 className="text-[15px] font-semibold">{group.name}</h3>
        <span className="text-[12.5px] text-[var(--color-text-faint)]">
          {group.tour ?? group.country ?? ""}
          {group.women ? " · women" : ""}
        </span>
        <span className="ml-auto text-[12.5px] text-[var(--color-text-faint)]">
          {group.matches.length}{" "}
          {group.matches.length === 1 ? "match" : "matches"}
        </span>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-[14px]">
          <thead>
            <tr className="text-left text-[12px] text-[var(--color-text-faint)]">
              <th className="px-4 py-2 font-medium">Time</th>
              <th className="px-4 py-2 font-medium">Match</th>
              <th className="px-4 py-2 font-medium">Win chance</th>
              <th className="px-4 py-2 font-medium">Engine backs</th>
              <th className="px-4 py-2 font-medium">Total</th>
              <th className="px-4 py-2 font-medium">Result</th>
            </tr>
          </thead>
          <tbody>
            {group.matches.map((match) => (
              <Row key={match.match_id} match={match} sport={sport} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function SportBoard({
  board,
  sport,
}: {
  board: Board;
  sport: OtherSportKey;
}) {
  if (board.competitions.length === 0) {
    return (
      <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
        <p className="text-[15px] font-medium">
          No {sport} matches on {shortDate(board.date)}
        </p>
        <p className="mt-2 max-w-[60ch] text-[14px] leading-relaxed text-[var(--color-text-dim)]">
          Either nothing is scheduled that day or it has not been loaded yet.
          Fixtures are pulled in on a schedule through the day, so an empty day
          here means nothing has arrived, not that nothing is being played.
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      {board.competitions.map((group) => (
        <Group
          key={`${group.tour}-${group.name}`}
          group={group}
          sport={sport}
        />
      ))}
    </div>
  );
}
