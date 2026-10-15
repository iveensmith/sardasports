"use client";

/**
 * Premium plans. The owner sets the real price here; nothing is pre-filled, and a plan is not
 * offered to the public until it is switched on.
 *
 * Prices are typed the way people say them (5000 for five thousand naira, 9.99 for nine pounds
 * ninety-nine) and stored in the currency's smallest unit, so there is never a fraction of a
 * penny to round.
 */

import { useState } from "react";
import { Check, Field, Message, inputClass } from "@/components/auth/ui";
import { useAdminData } from "@/components/admin/useAdminData";
import { api } from "@/lib/clientApi";
import { money, type PlanView } from "@/lib/content";

export function PlansAdmin() {
  const { data, error, loading, reload } = useAdminData<{ plans: PlanView[] }>(
    "admin/plans",
  );
  const providers = useAdminData<{ providers: string[] }>("premium/plans");
  const [message, setMessage] = useState<{ tone: "error" | "success"; text: string } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const f = new FormData(formElement);
    const price = Number(String(f.get("price") ?? "").replace(/,/g, ""));
    if (!Number.isFinite(price) || price <= 0) {
      setMessage({ tone: "error", text: "Enter a price above zero." });
      return;
    }
    setBusy(true);
    setMessage(null);
    const result = await api("/api/engine/admin/plans", {
      body: {
        code: String(f.get("code") ?? ""),
        name: String(f.get("name") ?? ""),
        description: String(f.get("description") ?? ""),
        price_minor: Math.round(price * 100),
        currency: String(f.get("currency") ?? ""),
        interval: String(f.get("interval") ?? "month"),
        active: f.get("active") === "on",
      },
    });
    setBusy(false);
    if (result.ok) {
      setMessage({ tone: "success", text: "Plan saved." });
      formElement.reset();
      await reload();
    } else {
      setMessage({
        tone: "error",
        text: result.error?.message ?? "Could not save the plan.",
      });
    }
  }

  const active = providers.data?.providers ?? [];

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-[28px] font-black tracking-[-0.02em]">Premium plans</h1>
        <p className="mt-1 max-w-[70ch] text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
          One payment buys one period (a month or a year). Nothing renews by
          itself. A plan only appears on the Premium page once it is switched on.
        </p>
      </header>

      <p
        className={`rounded-[var(--radius-md)] border px-4 py-3 text-[14px] ${
          active.length > 0
            ? "border-[var(--color-won)]/50 bg-[var(--color-won)]/10"
            : "border-[var(--color-gold)]/50 bg-[var(--color-gold)]/[0.07]"
        }`}
      >
        {active.length > 0 ? (
          <>
            Payment is on through <b>{active.join(" and ")}</b>.
          </>
        ) : (
          <>
            <b>No payment provider is configured.</b> Members cannot pay online
            yet. Add a Stripe or Paystack secret key to the server settings
            (see the deployment guide); until then you can give premium by hand
            from Members.
          </>
        )}
      </p>

      <section>
        <h2 className="text-[18px] font-bold">Current plans</h2>
        {loading && <p className="mt-3 text-[14px] text-[var(--color-text-dim)]">Loading…</p>}
        {error && <div className="mt-3"><Message tone="error">{error}</Message></div>}
        {data && data.plans.length === 0 && (
          <p className="mt-3 text-[14px] text-[var(--color-text-dim)]">
            No plans yet. Create one below.
          </p>
        )}
        <ul className="mt-4 space-y-3">
          {data?.plans.map((plan) => (
            <li
              key={plan.code}
              className="flex flex-wrap items-center justify-between gap-3 rounded-[12px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-4"
            >
              <div>
                <p className="text-[16px] font-bold">
                  {plan.name}{" "}
                  <span className="font-normal text-[var(--color-text-dim)]">
                    ({plan.code})
                  </span>
                </p>
                <p className="mt-0.5 text-[14px] tabular-nums">
                  {money(plan.price_minor, plan.currency)} per {plan.interval}
                </p>
              </div>
              <span
                className={`rounded px-2 py-1 text-[11px] font-extrabold tracking-wider uppercase ${
                  plan.active
                    ? "bg-[var(--color-won)]/20 text-[var(--color-won)]"
                    : "bg-[var(--color-surface-raised)] text-[var(--color-text-dim)]"
                }`}
              >
                {plan.active ? "On sale" : "Off"}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-5 sm:p-6">
        <h2 className="text-[18px] font-bold">Create or change a plan</h2>
        <p className="mt-1 text-[13.5px] text-[var(--color-text-dim)]">
          Using the code of an existing plan updates that plan.
        </p>
        <form onSubmit={save} className="mt-4 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="code" name="code" label="Code" placeholder="monthly" required />
            <Field id="name" name="name" label="Name shown to members" placeholder="Monthly" required />
            <Field
              id="price"
              name="price"
              label="Price"
              placeholder="5000"
              inputMode="decimal"
              required
              hint="In the currency's main unit, e.g. 5000 or 9.99."
            />
            <Field
              id="currency"
              name="currency"
              label="Currency"
              placeholder="NGN"
              maxLength={3}
              required
              hint="Three letters: NGN, GBP, USD."
            />
            <div>
              <label htmlFor="interval" className="text-[13px] font-semibold">
                One payment lasts
              </label>
              <select
                id="interval"
                name="interval"
                defaultValue="month"
                className={`${inputClass} mt-1.5`}
              >
                <option value="month">A month</option>
                <option value="year">A year</option>
              </select>
            </div>
            <Field
              id="description"
              name="description"
              label="Short description (optional)"
              maxLength={300}
            />
          </div>
          <Check id="active" name="active">
            Switch this plan on (show it on the Premium page).
          </Check>
          {message && <Message tone={message.tone}>{message.text}</Message>}
          <button
            type="submit"
            disabled={busy}
            className="nt-cta nt-cta--primary disabled:opacity-60"
          >
            {busy ? "Saving…" : "Save plan"}
          </button>
        </form>
      </section>
    </div>
  );
}
