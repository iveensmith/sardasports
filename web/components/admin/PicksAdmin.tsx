"use client";

/**
 * Write, publish, settle and delete the editor's picks.
 *
 * The rules shown here are enforced by the engine, not by this screen: a published pick cannot
 * be edited; it can be deleted only until its match kicks off; after that it is settled (won,
 * lost) or voided with a reason, and stays on the public record.
 */

import { useState } from "react";
import {
  Check,
  Field,
  Message,
  inputClass,
} from "@/components/auth/ui";
import { useAdminData } from "@/components/admin/useAdminData";
import { LocalTime } from "@/components/LocalTime";
import { api } from "@/lib/clientApi";
import type { EditorPick, PicksRecord } from "@/lib/content";

const MARKET_SUGGESTIONS = [
  "Match result",
  "Double chance",
  "Draw no bet",
  "Total goals",
  "Both teams to score",
  "Asian handicap",
  "Moneyline",
  "Total points",
  "Set betting",
];

function isAfterKickoff(pick: EditorPick): boolean {
  const iso = /[zZ]|[+-]\d\d:?\d\d$/.test(pick.kickoff)
    ? pick.kickoff
    : `${pick.kickoff}Z`;
  return new Date(iso).getTime() <= Date.now();
}

const BADGE: Record<string, string> = {
  pending: "text-[var(--color-text-dim)]",
  won: "text-[var(--color-won)]",
  lost: "text-[var(--color-lost)]",
  void: "text-[var(--color-text-faint)]",
};

export function PicksAdmin() {
  const { data, error, loading, reload } = useAdminData<{
    picks: EditorPick[];
    record: PicksRecord;
  }>("admin/picks");
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create(publish: boolean, form: HTMLFormElement) {
    const f = new FormData(form);
    const kickoffLocal = String(f.get("kickoff") ?? "");
    if (!kickoffLocal) {
      setFormError("Choose the kick-off date and time.");
      return;
    }
    setBusy(true);
    setFormError(null);
    setNotice(null);
    const odds = String(f.get("odds") ?? "").trim();
    const confidence = String(f.get("confidence") ?? "").trim();
    const result = await api("/api/engine/admin/picks", {
      body: {
        sport: String(f.get("sport") ?? "football"),
        competition: String(f.get("competition") ?? ""),
        home_team: String(f.get("home") ?? ""),
        away_team: String(f.get("away") ?? ""),
        // The field is in the administrator's own time zone; send it as UTC.
        kickoff: new Date(kickoffLocal).toISOString(),
        market: String(f.get("market") ?? ""),
        selection: String(f.get("selection") ?? ""),
        odds: odds ? Number(odds) : null,
        confidence: confidence ? Number(confidence) : null,
        rationale: String(f.get("rationale") ?? ""),
        premium_only: f.get("premium") === "on",
        publish,
      },
    });
    setBusy(false);
    if (result.ok) {
      setNotice(publish ? "Published." : "Saved as a draft.");
      form.reset();
      await reload();
    } else {
      setFormError(result.error?.message ?? "Could not save the pick.");
    }
  }

  async function action(
    label: string,
    path: string,
    options: { method?: string; body?: unknown } = {},
  ) {
    setNotice(null);
    setFormError(null);
    const result = await api(`/api/engine/${path}`, {
      method: options.method ?? "POST",
      body: options.body ?? (options.method === "DELETE" ? undefined : {}),
    });
    if (result.ok) {
      setNotice(label);
      await reload();
    } else {
      setFormError(result.error?.message ?? "That did not work.");
    }
  }

  function settle(pick: EditorPick, result: "won" | "lost" | "void") {
    let reason: string | undefined;
    if (result === "void") {
      const entered = window.prompt(
        "Why is this pick void? This is shown publicly next to the pick.",
      );
      if (!entered || !entered.trim()) return;
      reason = entered.trim();
    }
    void action(`Marked ${result}.`, `admin/picks/${pick.id}/settle`, {
      body: { result, void_reason: reason },
    });
  }

  function remove(pick: EditorPick) {
    const warning = pick.status === "published"
      ? "Delete this published pick? It is not yet kicked off, so it can still be removed. This cannot be undone."
      : "Delete this draft?";
    if (window.confirm(warning)) {
      void action("Deleted.", `admin/picks/${pick.id}`, { method: "DELETE" });
    }
  }

  const record = data?.record;

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-[28px] font-black tracking-[-0.02em]">Picks</h1>
        <p className="mt-1 max-w-[70ch] text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
          Your own predictions. Publish a pick before the match; it cannot be
          edited afterwards. You can delete it until kick-off. After that it
          stays on the record and can only be settled or voided with a reason.
        </p>
      </header>

      <section className="rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-5 sm:p-6">
        <h2 className="text-[18px] font-bold">New pick</h2>
        <form
          className="mt-4 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
          }}
          id="pick-form"
        >
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label htmlFor="sport" className="text-[13px] font-semibold">
                Sport
              </label>
              <select
                id="sport"
                name="sport"
                defaultValue="football"
                className={`${inputClass} mt-1.5`}
              >
                <option value="football">Football</option>
                <option value="basketball">Basketball</option>
                <option value="tennis">Tennis</option>
              </select>
            </div>
            <div className="sm:col-span-2">
              <Field
                id="competition"
                name="competition"
                label="Competition"
                placeholder="Premier League"
                required
              />
            </div>
            <Field id="home" name="home" label="Home team or player" required />
            <Field id="away" name="away" label="Away team or player" required />
            <Field
              id="kickoff"
              name="kickoff"
              type="datetime-local"
              label="Kick-off (your time)"
              required
            />
            <div>
              <Field
                id="market"
                name="market"
                label="Market"
                list="market-suggestions"
                placeholder="Total goals"
                required
              />
              <datalist id="market-suggestions">
                {MARKET_SUGGESTIONS.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            </div>
            <Field
              id="selection"
              name="selection"
              label="Selection"
              placeholder="Over 2.5"
              required
            />
            <Field
              id="odds"
              name="odds"
              type="number"
              step="0.01"
              min="1.01"
              label="Odds (optional)"
              placeholder="1.85"
            />
            <Field
              id="confidence"
              name="confidence"
              type="number"
              min="1"
              max="100"
              label="Confidence % (optional)"
              placeholder="70"
            />
          </div>
          <div>
            <label htmlFor="rationale" className="text-[13px] font-semibold">
              Reasoning (shown with the pick)
            </label>
            <textarea
              id="rationale"
              name="rationale"
              rows={3}
              maxLength={4000}
              className={`${inputClass} mt-1.5`}
            />
          </div>
          <Check id="premium" name="premium">
            Premium pick: hidden from non-members until kick-off.
          </Check>
          {formError && <Message tone="error">{formError}</Message>}
          {notice && <Message tone="success">{notice}</Message>}
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                create(true, document.getElementById("pick-form") as HTMLFormElement)
              }
              className="nt-cta nt-cta--primary disabled:opacity-60"
            >
              Publish now
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                create(false, document.getElementById("pick-form") as HTMLFormElement)
              }
              className="nt-cta nt-cta--ghost disabled:opacity-60"
            >
              Save draft
            </button>
          </div>
        </form>
      </section>

      {record && (
        <p className="text-[14px] text-[var(--color-text-dim)]">
          Record: <b className="text-[var(--color-text)]">{record.won}</b> won,{" "}
          <b className="text-[var(--color-text)]">{record.lost}</b> lost,{" "}
          {record.void} void, {record.pending} to play
          {record.win_rate !== null ? ` (${record.win_rate}% won)` : ""}.
        </p>
      )}

      <section>
        <h2 className="text-[18px] font-bold">All picks</h2>
        {loading && <p className="mt-3 text-[14px] text-[var(--color-text-dim)]">Loading…</p>}
        {error && <div className="mt-3"><Message tone="error">{error}</Message></div>}
        {data && data.picks.length === 0 && (
          <p className="mt-3 text-[14px] text-[var(--color-text-dim)]">
            No picks yet.
          </p>
        )}
        <ul className="mt-4 space-y-3">
          {data?.picks.map((pick) => {
            const started = isAfterKickoff(pick);
            const published = pick.status === "published";
            return (
              <li
                key={pick.id}
                className="rounded-[12px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[12.5px] text-[var(--color-text-dim)]">
                      {pick.competition} ·{" "}
                      <LocalTime iso={pick.kickoff} withDate utcSuffix />
                    </p>
                    <p className="mt-0.5 text-[16px] font-bold">
                      {pick.home_team} v {pick.away_team}
                    </p>
                    <p className="mt-1 text-[14px]">
                      {pick.market}: <b>{pick.selection}</b>
                      {pick.odds !== null && ` @ ${pick.odds.toFixed(2)}`}
                      {pick.premium_only && (
                        <span className="ml-2 rounded bg-[var(--color-gold)] px-1.5 py-0.5 text-[10px] font-extrabold tracking-wider text-[var(--color-ink-on-accent)] uppercase">
                          Premium
                        </span>
                      )}
                    </p>
                  </div>
                  <div className="text-right text-[12.5px]">
                    <p className="font-bold uppercase">
                      {published ? "Published" : "Draft"}
                    </p>
                    <p className={`font-bold uppercase ${BADGE[pick.result]}`}>
                      {pick.result}
                    </p>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  {!published && (
                    <button
                      type="button"
                      className="nt-cta nt-cta--primary !px-3 !py-1.5 text-[12px]"
                      onClick={() =>
                        action("Published.", `admin/picks/${pick.id}/publish`)
                      }
                    >
                      Publish
                    </button>
                  )}
                  {published && started && pick.result === "pending" && (
                    <>
                      <button
                        type="button"
                        className="nt-cta nt-cta--ghost !px-3 !py-1.5 text-[12px]"
                        onClick={() => settle(pick, "won")}
                      >
                        Mark won
                      </button>
                      <button
                        type="button"
                        className="nt-cta nt-cta--ghost !px-3 !py-1.5 text-[12px]"
                        onClick={() => settle(pick, "lost")}
                      >
                        Mark lost
                      </button>
                    </>
                  )}
                  {published && pick.result !== "void" && started && (
                    <button
                      type="button"
                      className="nt-cta nt-cta--ghost !px-3 !py-1.5 text-[12px]"
                      onClick={() => settle(pick, "void")}
                    >
                      Void with reason
                    </button>
                  )}
                  {(!published || !started) && (
                    <button
                      type="button"
                      className="nt-cta !px-3 !py-1.5 text-[12px] border-[var(--color-lost)] text-[var(--color-lost)] hover:bg-[var(--color-lost)]/10"
                      onClick={() => remove(pick)}
                    >
                      Delete
                    </button>
                  )}
                  {published && started && (
                    <span className="self-center text-[12px] text-[var(--color-text-faint)]">
                      Kicked off: this pick stays on the record.
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
