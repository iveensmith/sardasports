import Link from "next/link";
import { CheckoutButton } from "@/components/premium/CheckoutButton";
import { Check as TickIcon } from "@/components/home/icons";
import { getProgress } from "@/lib/api";
import { money, type PlanView } from "@/lib/content";
import { rate } from "@/lib/progress";
import { engineCall, getSession } from "@/lib/session";
import { pageMetadata } from "@/lib/seo";

// Per request: it shows whether the viewer is signed in and already a member.
export const dynamic = "force-dynamic";

export const metadata = pageMetadata({
  title: "Premium: Unlock Every Football Prediction",
  description:
    "15 football predictions are free every day. Premium unlocks all the rest before kick-off, plus the editor's premium picks. Every prediction is graded in public.",
  path: "/premium",
});

/** How many predictions a day are free. Keep in step with `FREE_DAILY_LIMIT` in the engine. */
const FREE_PER_DAY = 15;

const INCLUDED = [
  "Every football prediction, before kick-off: the pick, its confidence and every market",
  "The estimator breakdown, expected goals and the full match analysis",
  "All of the day's banker picks, and the slip of the day built from them",
  "The editor's premium picks before kick-off, and the full text of premium posts",
];

const STAYS_FREE = [
  `${FREE_PER_DAY} predictions every day, in full, with no account needed`,
  "Every prediction once its match kicks off, with the result beside it",
  "The record: live and reconstructed, wins and losses, counted apart",
  "Live scores, results and league tables",
];

function intervalLabel(interval: string): string {
  if (interval === "year") return "a year";
  if (interval === "week") return "a week";
  return "a month";
}

/** The saving of paying for a longer plan instead of repeating a shorter one, as a whole percent. */
function saving(long: PlanView | undefined, short: PlanView | undefined, times: number): number | null {
  if (!long || !short || long.currency !== short.currency) return null;
  const percent = Math.round((1 - long.price_minor / (short.price_minor * times)) * 100);
  return percent >= 5 ? percent : null;
}

export default async function PremiumPage({
  searchParams,
}: {
  searchParams: Promise<{ cancelled?: string }>;
}) {
  const { cancelled } = await searchParams;
  const [session, plansResult, progress] = await Promise.all([
    getSession(),
    engineCall<{ plans: PlanView[]; providers: string[] }>("/premium/plans"),
    getProgress().catch(() => null),
  ]);
  const plans = plansResult.data?.plans ?? [];
  const providers = plansResult.data?.providers ?? [];
  const payable = providers.length > 0;
  const member = session?.entitlement.premium ?? false;

  const byInterval = (interval: string) => plans.find((p) => p.interval === interval);
  const weekly = byInterval("week");
  const monthly = byInterval("month");
  const yearly = byInterval("year");
  // 52 weeks and 12 months make a year; 4.345 weeks make a month.
  const monthlySaving = saving(monthly, weekly, 4.345);
  const yearlySaving = saving(yearly, monthly, 12);
  const overall = progress?.overall ?? null;
  const liveSettled = progress?.live.record.settled ?? 0;

  return (
    <div className="mx-auto w-full max-w-[1040px] px-4 py-12 sm:px-6 sm:py-16">
      <header className="max-w-[66ch]">
        <p className="text-[12px] font-extrabold tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
          Premium
        </p>
        <h1 className="mt-2 text-[clamp(2rem,5vw,3rem)] leading-[1.05] font-black tracking-[-0.025em]">
          Unlock every prediction.{" "}
          <span className="text-[var(--color-gold)]">{FREE_PER_DAY} are free every day.</span>
        </h1>
        <p className="mt-4 text-[16px] leading-relaxed text-[var(--color-text-dim)]">
          Every day {FREE_PER_DAY} football predictions are free, in full. Premium opens all
          the rest before kick-off. Once a match kicks off its prediction is open to everyone,
          with the result beside it, so the record can always be checked.
        </p>
      </header>

      {overall && overall.settled > 0 && (
        <section
          aria-label="The record"
          className="mt-8 grid grid-cols-3 overflow-hidden rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-surface)]"
        >
          {[
            { value: rate(overall), label: "of graded predictions came in" },
            { value: overall.settled.toLocaleString("en-GB"), label: "predictions graded" },
            { value: String(FREE_PER_DAY), label: "free every day" },
          ].map((tile, index) => (
            <div
              key={tile.label}
              className={`px-4 py-5 sm:px-6 ${index > 0 ? "border-l border-[var(--color-line)]" : ""}`}
            >
              <p className="text-[clamp(1.4rem,4vw,2rem)] leading-none font-black tabular-nums text-[var(--color-gold-bright)]">
                {tile.value}
              </p>
              <p className="mt-1.5 text-[12px] leading-snug text-[var(--color-text-dim)] sm:text-[13px]">
                {tile.label}
              </p>
            </div>
          ))}
          <p className="col-span-3 border-t border-[var(--color-line)] px-4 py-3 text-[12px] text-[var(--color-text-faint)] sm:px-6">
            Wins and losses both stay on the record.{" "}
            {liveSettled > 0
              ? `${liveSettled.toLocaleString("en-GB")} of these predictions were stored before kick-off; the other ${(overall.settled - liveSettled).toLocaleString("en-GB")} were rebuilt afterwards from history.`
              : "None of these were stored before kick-off yet: they were all rebuilt afterwards from history."}{" "}
            The two are counted apart on{" "}
            <Link href="/progress" className="underline underline-offset-4">
              the record page
            </Link>
            .
          </p>
        </section>
      )}

      {cancelled && (
        <p className="mt-6 rounded-[var(--radius-md)] border border-[var(--color-line-strong)] bg-[var(--color-surface-raised)] px-4 py-3 text-[14px]">
          The payment was cancelled. Nothing was charged.
        </p>
      )}

      <section className="mt-10" aria-labelledby="plans">
        <h2 id="plans" className="text-[22px] font-bold">
          Choose your plan
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
            Premium is not open for sign-up yet. The {FREE_PER_DAY} free predictions a day are
            there in the meantime.
          </p>
        ) : (
          <div className="mt-5 grid gap-4 md:grid-cols-3">
            {plans.map((plan) => {
              const badge =
                plan.code === yearly?.code && yearlySaving
                  ? `Best value: save ${yearlySaving}%`
                  : plan.code === monthly?.code && monthlySaving
                    ? `Save ${monthlySaving}% on weekly`
                    : null;
              const highlighted = plan.code === yearly?.code && badge !== null;
              return (
                <div
                  key={plan.code}
                  className={`relative flex flex-col rounded-[14px] border bg-[var(--color-surface)] p-6 ${
                    highlighted
                      ? "border-2 border-[var(--color-gold)]/80"
                      : "border-[var(--color-line-strong)]"
                  }`}
                >
                  {badge && (
                    <span className="absolute -top-3 left-5 rounded-full bg-[var(--color-gold)] px-3 py-1 text-[11px] font-extrabold tracking-wide text-[var(--color-ink-on-accent)] uppercase">
                      {badge}
                    </span>
                  )}
                  <p className="text-[14px] font-extrabold tracking-wider text-[var(--color-text-dim)] uppercase">
                    {plan.name}
                  </p>
                  <p className="mt-2 text-[34px] leading-none font-black tabular-nums">
                    {money(plan.price_minor, plan.currency)}
                    <span className="ml-1.5 text-[14px] font-medium text-[var(--color-text-dim)]">
                      {intervalLabel(plan.interval)}
                    </span>
                  </p>
                  {plan.interval === "year" && (
                    <p className="mt-1.5 text-[13px] text-[var(--color-text-dim)] tabular-nums">
                      That is {money(Math.round(plan.price_minor / 12), plan.currency)} a month
                    </p>
                  )}
                  {plan.description && (
                    <p className="mt-3 text-[14px] leading-relaxed text-[var(--color-text-dim)]">
                      {plan.description}
                    </p>
                  )}
                  <p className="mt-3 text-[12.5px] text-[var(--color-text-faint)]">
                    One payment, no automatic renewal: it never charges you again unless you
                    choose to.
                  </p>
                  <div className="mt-auto pt-5">
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
                        Online payment is being switched on. Please check back soon.
                      </p>
                    ) : (
                      <CheckoutButton
                        planCode={plan.code}
                        label={member ? "Add more time" : "Get premium"}
                      />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <div className="mt-10 grid gap-5 md:grid-cols-2">
        <section className="rounded-[14px] border-2 border-[var(--color-gold)]/80 bg-[var(--color-surface)] p-6">
          <h2 className="text-[18px] font-bold">What premium unlocks</h2>
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

      <p className="mt-8 text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
        Prices are in US dollars so a card from any country works. Payment is taken on the payment
        provider&rsquo;s own page; this site never sees or stores your card details. Premium
        access is for 18s and over. For information only, not betting advice: a prediction is a
        probability, not a promise.
      </p>
    </div>
  );
}
