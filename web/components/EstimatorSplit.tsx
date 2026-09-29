/**
 * Which independent estimators back the pick.
 *
 * The engine runs three genuinely separate result estimators — Elo, Poisson
 * and a trained model — and then blends them. The blend is the answer, and
 * it necessarily averages away the most interesting thing: a 2-vs-1 split
 * can come out as a tidy near-even prediction that hides a real argument
 * between the three.
 *
 * Shown as "2 of 3 agree" with each estimator's own pick named, never as a
 * colour-coded dot alone — the reader should be able to see *which* one
 * dissented and on what.
 */

import type { Agreement } from "@/lib/api";

const OUTCOME_LABEL: Record<string, string> = {
  home: "home",
  draw: "draw",
  away: "away",
};

const ESTIMATOR_LABEL: Record<string, string> = {
  elo: "Elo",
  poisson: "Poisson",
  xgboost: "Model",
};

export function AgreementPill({ agreement }: { agreement: Agreement | null }) {
  if (!agreement) return null;
  const { agreeing, total, unanimous } = agreement;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-medium whitespace-nowrap"
      style={{
        borderColor: unanimous
          ? "var(--color-line-strong)"
          : "var(--color-away)",
        color: unanimous ? "var(--color-text-dim)" : "var(--color-away)",
      }}
      title={
        unanimous
          ? `All ${total} estimators back the ${OUTCOME_LABEL[agreement.pick]} pick`
          : `Only ${agreeing} of ${total} estimators back the ${OUTCOME_LABEL[agreement.pick]} pick`
      }
    >
      {agreeing}/{total} agree
    </span>
  );
}

export function EstimatorBreakdown({
  agreement,
  homeLabel,
  awayLabel,
}: {
  agreement: Agreement | null;
  homeLabel: string;
  awayLabel: string;
}) {
  if (!agreement) return null;

  const named = (outcome: string | null) => {
    if (outcome === "home") return homeLabel;
    if (outcome === "away") return awayLabel;
    if (outcome === "draw") return "Draw";
    return "—";
  };

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[15px] font-semibold">How the estimators voted</h3>
        <AgreementPill agreement={agreement} />
      </div>
      <p className="mt-1 mb-4 max-w-[66ch] text-[13px] leading-relaxed text-[var(--color-text-dim)]">
        {agreement.unanimous
          ? "All three independent estimators favour the same outcome. That is the strongest form this engine has: they are built on different evidence and still land together."
          : "The estimators disagree. The headline probability is their weighted blend, which means it sits between genuinely different readings of this match rather than reflecting a settled view."}
      </p>

      <ul className="space-y-2">
        {Object.entries(agreement.by_estimator).map(([name, pick]) => {
          const backs = pick === agreement.pick;
          return (
            <li
              key={name}
              className="flex items-center justify-between gap-4 border-t border-[var(--color-line)] pt-2 text-[14px]"
            >
              <span className="text-[var(--color-text-dim)]">
                {ESTIMATOR_LABEL[name] ?? name}
              </span>
              <span className="flex items-center gap-2">
                <span>{named(pick)}</span>
                <span
                  className="text-[12px]"
                  style={{
                    color: backs
                      ? "var(--color-text-faint)"
                      : "var(--color-away)",
                  }}
                >
                  {backs ? "backs the pick" : "dissents"}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
