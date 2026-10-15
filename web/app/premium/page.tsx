import Link from "next/link";
import { CheckoutButton } from "@/components/premium/CheckoutButton";
import { Check as TickIcon } from "@/components/home/icons";
import { money, type PlanView } from "@/lib/content";
import { engineCall, getSession } from "@/lib/session";
import { pageMetadata } from "@/lib/seo";

// Per request: it shows whether the viewer is signed in and already a member.
export const dynamic = "force-dynamic";

export const metadata = pageMetadata({
  title: "Premium",
  description:
    "SARDASPORTS premium: early access to the editor's picks and the full write-ups. The engine's predictions and the record stay free.",
  path: "/premium",
});

const INCLUDED = [
  "The editor's premium picks before kick-off (everyone sees them from kick-off, with the result)",
  "The full text of premium blog posts",
];

const STAYS_FREE = [
  "Every engine prediction on every board",
  "The record: live and reconstructed, wins and losses",
  "Live scores, results and league tables",
];

function intervalLabel(interval: string): string {
  return interval === "year" ? "a year" : "a month";
}

export default async function PremiumPage({
  searchParams,
}: {
  searchParams: Promise<{ cancelled?: string }>;
}) {
  const { cancelled } = await searchParams;
  const [session, plansResult] = await Promise.all([
    getSession(),
    engineCall<{ plans: PlanView[]; providers: string[] }>("/premium/plans"),
  ]);
  const plans = plansResult.data?.plans ?? [];
  const providers = plansResult.data?.providers ?? [];
  const payable = providers.length > 0;
  const member = session?.entitlement.premium ?? false;

  return (
    <div className="mx-auto w-full max-w-[920px] px-4 py-12 sm:px-6 sm:py-16">
      <header className="max-w-[62ch]">
        <p className="text-[12px] font-extrabold tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
          Premium
        </p>
        <h1 className="mt-2 text-[clamp(2rem,5vw,3rem)] leading-[1.05] font-black tracking-[-0.025em]">
          More from the editor.{" "}
          <span className="text-[var(--color-gold)]">Nothing taken from the record.</span>
        </h1>
        <p className="mt-4 text-[16px] leading-relaxed text-[var(--color-text-dim)]">
          Premium pays for the editor&rsquo;s own work: picks you see early and
          the full write-ups. It does not put the engine&rsquo;s predictions or
          the record behind a wall, and a premium pick is on the public record
          from kick-off, win or lose.
        </p>
      </header>

      {cancelled && (
        <p className="mt-6 rounded-[var(--radius-md)] border border-[var(--color-line-strong)] bg-[var(--color-surface-raised)] px-4 py-3 text-[14px]">
          The payment was cancelled. Nothing was charged.
        </p>
      )}

      <div className="mt-10 grid gap-5 md:grid-cols-2">
        <section className="rounded-[14px] border-2 border-[var(--color-gold)]/80 bg-[var(--color-surface)] p-6">
          <h2 className="text-[18px] font-bold">What premium includes</h2>
          <ul className="mt-4 space-y-3">
            {INCLUDED.map((item) => (
              <li key={item} className="flex gap-3 text-[14.5px] leading-snug">
                <span className="mt-0.5 text-[var(--color-gold-bright)]">
                  <TickIcon size={18} />
                </span>
                {item}
              </li>
            ))}
          </ul>
        </section>
        <section className="rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6">
          <h2 className="text-[18px] font-bold">What stays free, always</h2>
          <ul className="mt-4 space-y-3">
            {STAYS_FREE.map((item) => (
              <li key={item} className="flex gap-3 text-[14.5px] leading-snug">
                <span className="mt-0.5 text-[var(--color-won)]">
                  <TickIcon size={18} />
                </span>
                {item}
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="mt-10" aria-labelledby="plans">
        <h2 id="plans" className="text-[22px] font-bold">
          Choose how long
        </h2>

        {member && (
          <p className="mt-3 rounded-[var(--radius-md)] border border-[var(--color-won)]/50 bg-[var(--color-won)]/10 px-4 py-3 text-[14px]">
            You have premium
            {session?.entitlement.until
              ? ` until ${new Date(`${session.entitlement.until}Z`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}`
              : ""}
            . Paying again adds time to the end of your current period.
          </p>
        )}

        {plans.length === 0 ? (
          <p className="mt-4 rounded-[14px] border border-dashed border-[var(--color-line-strong)] p-6 text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
            Premium is not open for sign-up yet. Everything on the site stays
            free in the meantime.
          </p>
        ) : (
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {plans.map((plan) => (
              <div
                key={plan.code}
                className="flex flex-col rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-6"
              >
                <p className="text-[14px] font-extrabold tracking-wider text-[var(--color-text-dim)] uppercase">
                  {plan.name}
                </p>
                <p className="mt-2 text-[34px] leading-none font-black tabular-nums">
                  {money(plan.price_minor, plan.currency)}
                  <span className="ml-1.5 text-[14px] font-medium text-[var(--color-text-dim)]">
                    {intervalLabel(plan.interval)}
                  </span>
                </p>
                {plan.description && (
                  <p className="mt-3 text-[14px] leading-relaxed text-[var(--color-text-dim)]">
                    {plan.description}
                  </p>
                )}
                <p className="mt-3 text-[12.5px] text-[var(--color-text-faint)]">
                  One payment, no automatic renewal: it never charges you again
                  unless you choose to.
                </p>
                <div className="mt-5">
                  {!session ? (
                    <Link
                      href="/login?next=/premium"
                      className="nt-cta nt-cta--primary w-full"
                    >
                      Log in to subscribe
                    </Link>
                  ) : !session.user.email_verified ? (
                    <p className="text-[13.5px] text-[var(--color-text-dim)]">
                      Confirm your e-mail address first; we sent you a link.
                    </p>
                  ) : !payable ? (
                    <p className="text-[13.5px] text-[var(--color-text-dim)]">
                      Online payment is being switched on. Please check back
                      soon.
                    </p>
                  ) : (
                    <CheckoutButton
                      planCode={plan.code}
                      label={member ? "Add more time" : "Get premium"}
                    />
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        <p className="mt-6 text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
          Payment is taken on the payment provider&rsquo;s own page; this site
          never sees or stores your card details. Premium access is for 18s and
          over. For information only, not betting advice: a pick is a
          probability, not a promise.
        </p>
      </section>
    </div>
  );
}
