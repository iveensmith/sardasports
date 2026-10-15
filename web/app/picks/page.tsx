import Link from "next/link";
import { LocalTime } from "@/components/LocalTime";
import { SportMark } from "@/components/sport/SportMark";
import type { EditorPick, PicksRecord } from "@/lib/content";
import { engineCall, sessionToken } from "@/lib/session";
import { pageMetadata } from "@/lib/seo";

// Per request: a premium pick is shown or hidden depending on who is looking.
export const dynamic = "force-dynamic";

export const metadata = pageMetadata({
  title: "Editor's picks",
  description:
    "Hand-written picks from the SARDASPORTS editor, published before kick-off and settled in public, wins and losses alike.",
  path: "/picks",
});

const RESULT_LABEL: Record<EditorPick["result"], { text: string; color: string }> = {
  pending: { text: "To play", color: "var(--color-text-faint)" },
  won: { text: "Won", color: "var(--color-won)" },
  lost: { text: "Lost", color: "var(--color-lost)" },
  void: { text: "Void", color: "var(--color-text-faint)" },
};

function PickCard({ pick }: { pick: EditorPick }) {
  const result = RESULT_LABEL[pick.result];
  return (
    <li className="rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[12.5px] text-[var(--color-text-dim)]">
        <span className="flex items-center gap-2">
          <SportMark sport={pick.sport} size={15} />
          {pick.competition}
        </span>
        <span className="flex items-center gap-2 tabular-nums">
          <LocalTime iso={pick.kickoff} withDate utcSuffix />
        </span>
      </div>

      <p className="mt-2 text-[17px] font-bold">
        {pick.home_team} <span className="font-normal text-[var(--color-text-faint)]">v</span>{" "}
        {pick.away_team}
      </p>

      {pick.locked ? (
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded-[var(--radius-md)] border border-dashed border-[var(--color-gold)]/60 bg-[var(--color-gold)]/[0.06] px-3.5 py-3">
          <span className="rounded bg-[var(--color-gold)] px-1.5 py-0.5 text-[10px] font-extrabold tracking-wider text-[var(--color-ink-on-accent)] uppercase">
            Premium
          </span>
          <span className="text-[14px] text-[var(--color-text-dim)]">
            The pick is shown to premium members now, and to everyone from
            kick-off.
          </span>
          <Link
            href="/premium"
            className="text-[13.5px] font-semibold text-[var(--color-gold-bright)] underline underline-offset-4"
          >
            See premium
          </Link>
        </div>
      ) : (
        <div className="mt-3">
          <p className="rounded-md bg-[var(--color-gold)] px-3 py-2 text-[13.5px] font-extrabold tracking-[0.02em] text-[var(--color-ink-on-accent)] uppercase">
            {pick.market}: {pick.selection}
          </p>
          <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-[var(--color-text-dim)] tabular-nums">
            {pick.odds !== null && <span>Odds {pick.odds.toFixed(2)}</span>}
            {pick.confidence !== null && (
              <span>Confidence {pick.confidence}%</span>
            )}
            {pick.premium_only && (
              <span className="font-semibold text-[var(--color-gold-bright)]">
                Premium pick
              </span>
            )}
          </div>
          {pick.rationale && (
            <p className="mt-3 text-[14.5px] leading-relaxed">{pick.rationale}</p>
          )}
        </div>
      )}

      <p className="mt-3 text-[13px] font-bold" style={{ color: result.color }}>
        {result.text}
        {pick.result === "void" && pick.void_reason ? `: ${pick.void_reason}` : ""}
      </p>
    </li>
  );
}

export default async function PicksPage() {
  const token = await sessionToken();
  const [upcoming, recent, record] = await Promise.all([
    engineCall<{ picks: EditorPick[]; premium: boolean }>(
      "/content/picks?scope=upcoming&limit=30",
      { token },
    ),
    engineCall<{ picks: EditorPick[] }>("/content/picks?scope=recent&limit=20", {
      token,
    }),
    engineCall<PicksRecord>("/content/picks/record"),
  ]);
  const coming = upcoming.data?.picks ?? [];
  const past = recent.data?.picks ?? [];
  const stats = record.data;

  return (
    <div className="mx-auto w-full max-w-[860px] px-4 py-12 sm:px-6 sm:py-16">
      <header>
        <p className="text-[12px] font-extrabold tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
          Editor&rsquo;s picks
        </p>
        <h1 className="mt-2 text-[clamp(1.9rem,4.5vw,2.7rem)] leading-tight font-black tracking-[-0.02em]">
          Picks written by hand
        </h1>
        <p className="mt-3 max-w-[62ch] text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          These are the editor&rsquo;s own calls, separate from the engine&rsquo;s
          predictions and counted separately. A pick is published before
          kick-off, cannot be edited, and stays on this page with its result.
        </p>
      </header>

      {stats && stats.published > 0 && (
        <dl className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ["Settled", String(stats.settled)],
            ["Won", String(stats.won)],
            ["Lost", String(stats.lost)],
            [
              "Win rate",
              stats.win_rate === null ? "n/a" : `${stats.win_rate.toFixed(1)}%`,
            ],
          ].map(([label, value]) => (
            <div
              key={label}
              className="rounded-[12px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-4 text-center"
            >
              <dt className="text-[11px] font-extrabold tracking-[0.12em] text-[var(--color-text-dim)] uppercase">
                {label}
              </dt>
              <dd className="mt-1.5 text-[24px] font-black tabular-nums">
                {value}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <section className="mt-10" aria-labelledby="coming">
        <h2 id="coming" className="text-[20px] font-bold">
          Coming up
        </h2>
        {coming.length === 0 ? (
          <p className="mt-3 rounded-[14px] border border-dashed border-[var(--color-line-strong)] p-5 text-[14.5px] text-[var(--color-text-dim)]">
            No picks are published for upcoming matches right now.
          </p>
        ) : (
          <ul className="mt-4 space-y-3">
            {coming.map((pick) => (
              <PickCard key={pick.id} pick={pick} />
            ))}
          </ul>
        )}
      </section>

      {past.length > 0 && (
        <section className="mt-12" aria-labelledby="past">
          <h2 id="past" className="text-[20px] font-bold">
            Recent results
          </h2>
          <ul className="mt-4 space-y-3">
            {past.map((pick) => (
              <PickCard key={pick.id} pick={pick} />
            ))}
          </ul>
        </section>
      )}

      <p className="mt-12 border-t border-[var(--color-line)] pt-5 text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
        18+ &middot; For information only, not betting advice. Every pick is a
        probability, not a promise.
      </p>
    </div>
  );
}
