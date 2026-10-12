/**
 * One team: its form, recent results, what is next, and its league position.
 *
 * Everything is read from matches the engine holds. There is no squad list, no
 * player data and no market value on purpose — none of those are ingested, and
 * a plausible-looking number for any of them would be invented. The page also
 * says how old its newest result is, because most domestic seasons are between
 * rounds or over and "recent form" from months ago should not read as current.
 *
 * Next 16: `params` is a Promise and must be awaited.
 */

import { LocalTime } from "@/components/LocalTime";
import { utcDate } from "@/lib/time";
import Link from "next/link";
import { notFound } from "next/navigation";
import { TeamCrest } from "@/components/board/TeamCrest";
import { EngineError, getTeamPage } from "@/lib/api";
import type {
  FormLetter,
  TeamPageData,
  TeamRecentMatch,
  TeamUpcoming,
} from "@/lib/teams";
import type { SeasonStat, TeamFormSummary } from "@/lib/types";
import { JsonLd } from "@/components/seo/JsonLd";
import { breadcrumbLd, pageMetadata } from "@/lib/seo";

export const revalidate = 600;

/** Past this, "recent form" is last season's and should be labelled so. */
const STALE_AFTER_DAYS = 45;

/** Below this many recorded matches a team page is too thin to be indexed. */
const MIN_MATCHES_TO_INDEX = 3;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const page = await getTeamPage(slug).catch(() => null);
  if (!page) {
    return { title: "Team not found", robots: { index: false, follow: true } };
  }
  return pageMetadata({
    title: `${page.team.name} Predictions, Stats & Form`,
    description: `${page.team.name} form, recent results, next fixtures and season averages, with the engine's predictions for ${page.team.name} matches.`,
    path: `/teams/${slug}`,
    // A team with next to nothing on record is a thin page: no form, no table
    // position, little to say. It stays reachable and is not offered to search
    // engines until there is enough to be worth a result.
    noindex: page.recent_matches.length < MIN_MATCHES_TO_INDEX,
  });
}

const LETTER_STYLE: Record<FormLetter, { color: string; word: string }> = {
  W: { color: "var(--color-won)", word: "win" },
  D: { color: "var(--color-text-dim)", word: "draw" },
  L: { color: "var(--color-lost)", word: "loss" },
};

function FormChip({ letter }: { letter: FormLetter }) {
  const style = LETTER_STYLE[letter];
  return (
    <span
      className="inline-flex h-6 w-6 items-center justify-center rounded-[5px] border text-[11px] font-bold"
      style={{
        color: style.color,
        borderColor: `color-mix(in srgb, ${style.color} 40%, transparent)`,
        background: `color-mix(in srgb, ${style.color} 12%, transparent)`,
      }}
    >
      {letter}
      <span className="sr-only"> ({style.word})</span>
    </span>
  );
}

function Tile({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-4">
      <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
        {label}
      </p>
      <p className="mt-1.5 text-[24px] leading-none font-bold tabular-nums">
        {value}
      </p>
      {note && (
        <p className="mt-1.5 text-[12px] leading-relaxed text-[var(--color-text-faint)]">
          {note}
        </p>
      )}
    </div>
  );
}

function ordinal(n: number): string {
  const rest = n % 100;
  if (rest >= 11 && rest <= 13) return `${n}th`;
  return `${n}${{ 1: "st", 2: "nd", 3: "rd" }[n % 10] ?? "th"}`;
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

function pctOf(count: number, of: number): string {
  return of > 0 ? `${Math.round((100 * count) / of)}%` : "—";
}

function RecentRow({ match }: { match: TeamRecentMatch }) {
  const ours = match.is_home ? match.home_team : match.away_team;
  return (
    <li className="flex items-center gap-3 border-t border-[var(--color-line)] py-2.5 text-[13px] first:border-t-0">
      <span className="w-14 shrink-0 text-[11.5px] text-[var(--color-text-faint)]">
        {shortDate(match.match_date)}
      </span>
      {match.result && <FormChip letter={match.result} />}
      <Link
        href={`/match/${match.slug}`}
        className="min-w-0 flex-1 hover:text-[var(--color-gold-bright)]"
      >
        <span className="block truncate">
          <span className={match.is_home ? "font-semibold" : ""}>
            {match.home_team}
          </span>{" "}
          <span className="font-semibold tabular-nums">
            {match.home_score}&ndash;{match.away_score}
          </span>{" "}
          <span className={match.is_home ? "" : "font-semibold"}>
            {match.away_team}
          </span>
          <span className="sr-only"> ({ours} perspective)</span>
        </span>
        <span className="block truncate text-[11px] text-[var(--color-text-faint)]">
          {match.competition}
        </span>
      </Link>
    </li>
  );
}

function UpcomingRow({ match }: { match: TeamUpcoming }) {
  const at = utcDate(match.match_date);
  return (
    <li className="flex items-center gap-3 border-t border-[var(--color-line)] py-2.5 text-[13px] first:border-t-0">
      <span className="w-24 shrink-0 text-[11.5px] text-[var(--color-text-faint)]">
        {at.toLocaleDateString("en-GB", {
          day: "numeric",
          month: "short",
          timeZone: "UTC",
        })}
        , <LocalTime iso={match.match_date} />
      </span>
      <Link
        href={`/match/${match.slug}`}
        className="min-w-0 flex-1 hover:text-[var(--color-gold-bright)]"
      >
        <span className="block truncate font-medium">
          {match.home_team}{" "}
          <span className="text-[var(--color-text-faint)]">v</span>{" "}
          {match.away_team}
        </span>
        <span className="block truncate text-[11px] text-[var(--color-text-faint)]">
          {match.short_name}
        </span>
      </Link>
      <span className="text-[11.5px] text-[var(--color-gold-bright)]">
        See prediction
      </span>
    </li>
  );
}

const AVERAGES: Array<{
  key:
    | "shots"
    | "shots_on_target"
    | "corners"
    | "cards"
    | "possession"
    | "fouls"
    | "offsides";
  label: string;
  suffix?: string;
}> = [
  { key: "shots", label: "Shots" },
  { key: "shots_on_target", label: "Shots on target" },
  { key: "corners", label: "Corners" },
  { key: "cards", label: "Cards" },
  { key: "possession", label: "Possession", suffix: "%" },
  { key: "fouls", label: "Fouls" },
  { key: "offsides", label: "Offsides" },
];

function FormFacts({ form }: { form: TeamFormSummary }) {
  const n = form.matches_played;
  const rows: Array<[string, string]> = [
    ["Record", `${form.wins}W ${form.draws}D ${form.losses}L`],
    [
      "Goals scored",
      `${form.goals_scored} (${(form.goals_scored / Math.max(n, 1)).toFixed(2)} a match)`,
    ],
    [
      "Goals conceded",
      `${form.goals_conceded} (${(form.goals_conceded / Math.max(n, 1)).toFixed(2)} a match)`,
    ],
    ["Clean sheets", `${form.clean_sheets} of ${n}`],
    ["Over 2.5 goals", `${form.over_2_5} of ${n} (${pctOf(form.over_2_5, n)})`],
    ["Both teams scored", `${form.btts} of ${n} (${pctOf(form.btts, n)})`],
    ["Points a game", form.points_per_game.toFixed(2)],
  ];
  return (
    <dl className="grid gap-x-8 sm:grid-cols-2">
      {rows.map(([term, value]) => (
        <div
          key={term}
          className="flex items-baseline justify-between gap-4 border-t border-[var(--color-line)] py-2.5 text-[13px]"
        >
          <dt className="text-[var(--color-text-dim)]">{term}</dt>
          <dd className="font-medium tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Header({ page }: { page: TeamPageData }) {
  const { team, standing } = page;
  return (
    <header className="mb-8 flex flex-wrap items-center gap-5">
      <TeamCrest badge={team.badge} name={team.name} size={48} />
      <div>
        <p className="text-[11px] tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
          {standing
            ? standing.short_name
            : team.is_national
              ? "National team"
              : (team.country ?? "Team")}
        </p>
        <h1 className="mt-1.5 text-[clamp(1.9rem,4.5vw,2.6rem)] leading-tight font-bold tracking-[-0.02em]">
          {team.name} predictions and form
        </h1>
      </div>
    </header>
  );
}

export default async function TeamPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  let page: TeamPageData | null = null;
  let error: string | null = null;
  try {
    page = await getTeamPage(slug);
  } catch (e) {
    error =
      e instanceof EngineError || e instanceof Error
        ? e.message
        : "The engine could not be reached.";
  }

  if (error) {
    return (
      <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <p className="text-[15px] font-medium">The engine is unreachable</p>
          <p className="mt-2 text-[14px] text-[var(--color-text-dim)]">
            {error}
          </p>
        </div>
      </div>
    );
  }
  if (!page) notFound();

  const { team, standing, recent_matches: recent } = page;
  const newest = recent[0]?.match_date;
  const stale =
    page.last_match_age_days !== null &&
    page.last_match_age_days > STALE_AFTER_DAYS;
  const form10 = page.form_last10;
  const averages = AVERAGES.map((a) => ({
    ...a,
    stat: page.season_stats?.[a.key] as SeasonStat | undefined,
  })).filter((a) => a.stat && a.stat.value !== null);

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10">
      <JsonLd
        data={breadcrumbLd([
          { name: "Home", path: "/" },
          { name: "Leagues", path: "/leagues" },
          ...(standing
            ? [{ name: standing.short_name, path: `/leagues/${standing.slug}` }]
            : []),
          { name: team.name, path: `/teams/${team.slug}` },
        ])}
      />
      <Header page={page} />

      {stale && newest && (
        <p className="mb-6 max-w-[72ch] rounded-[var(--radius-lg)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] px-4 py-3 text-[13px] leading-relaxed text-[var(--color-text-dim)]">
          The newest result on record for {team.name} is from{" "}
          {new Date(newest).toLocaleDateString("en-GB", {
            day: "numeric",
            month: "long",
            year: "numeric",
            timeZone: "UTC",
          })}
          , so the form below describes that spell and not necessarily the
          team&rsquo;s current one.
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label="Engine rating"
          value={team.elo_rating.toFixed(0)}
          note="Elo, rebuilt from every result on record."
        />
        {standing && (
          <Tile
            label={`${standing.short_name} position`}
            value={`${ordinal(standing.position)} of ${standing.of}`}
            note={`${standing.row.points} points from ${standing.row.played} games${
              standing.season ? `, ${standing.season}` : ""
            }.`}
          />
        )}
        <Tile
          label="Goals a match"
          value={(
            form10.goals_scored / Math.max(form10.matches_played, 1)
          ).toFixed(2)}
          note={`Scored, over the last ${form10.matches_played}.`}
        />
        <div className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-4">
          <p className="text-[10.5px] tracking-wider text-[var(--color-text-faint)] uppercase">
            Recent form
          </p>
          <div className="mt-2.5 flex gap-1.5">
            {page.form_letters.length === 0 ? (
              <span className="text-[13px] text-[var(--color-text-faint)]">
                No results on record
              </span>
            ) : (
              page.form_letters.map((letter, index) => (
                <FormChip key={index} letter={letter} />
              ))
            )}
          </div>
          <p className="mt-2 text-[12px] text-[var(--color-text-faint)]">
            Newest first.
          </p>
        </div>
      </div>

      {page.upcoming.length > 0 && (
        <section className="mt-10" aria-label="Next matches">
          <h2 className="text-[15px] font-semibold">Next matches</h2>
          <ul className="mt-3 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] px-5 py-1">
            {page.upcoming.map((match) => (
              <UpcomingRow key={match.match_id} match={match} />
            ))}
          </ul>
        </section>
      )}

      <div className="mt-10 grid gap-10 lg:grid-cols-2">
        <section aria-label="Recent matches">
          <h2 className="text-[15px] font-semibold">Recent matches</h2>
          {recent.length === 0 ? (
            <p className="mt-3 text-[14px] text-[var(--color-text-dim)]">
              No completed matches on record.
            </p>
          ) : (
            <ul className="mt-3 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] px-5 py-1">
              {recent.map((match) => (
                <RecentRow key={match.match_id} match={match} />
              ))}
            </ul>
          )}
        </section>

        <section aria-label={`Last ${form10.matches_played} matches`}>
          <h2 className="text-[15px] font-semibold">
            Last {form10.matches_played} matches
          </h2>
          <div className="mt-3 rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] px-5 py-1">
            <FormFacts form={form10} />
          </div>
        </section>
      </div>

      {averages.length > 0 && page.season_stats && (
        <section className="mt-10" aria-label="Season averages">
          <h2 className="text-[15px] font-semibold">
            Season averages
            <span className="ml-2 text-[12px] font-normal text-[var(--color-text-faint)]">
              {page.season_stats.season} · per match
            </span>
          </h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {averages.map((a) => (
              <Tile
                key={a.key}
                label={a.label}
                value={`${a.stat!.value!.toFixed(a.key === "possession" ? 0 : 1)}${a.suffix ?? ""}`}
                note={`From ${a.stat!.sample_size} of ${page.season_stats!.matches_played} matches that recorded it.`}
              />
            ))}
          </div>
        </section>
      )}

      {standing && (
        <p className="mt-10 text-[13px] text-[var(--color-text-dim)]">
          See the full{" "}
          <Link
            className="text-[var(--color-gold-bright)] hover:underline"
            href={`/leagues/${standing.slug}?tab=standings`}
          >
            {standing.competition} table
          </Link>
          .
        </p>
      )}
    </div>
  );
}
