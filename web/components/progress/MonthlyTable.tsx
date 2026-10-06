/**
 * The last twelve months, every rate beside the sample it is measured over.
 *
 * Every month in the window gets a row, including ones with nothing settled —
 * those read "no settled calls" rather than being skipped. The record is not
 * continuous (predictions exist only where the engine was asked to price a
 * fixture), and a table that closed the gaps up would imply a run that
 * never happened.
 *
 * The "live" column is the part of each month's sample that was stored before
 * kick-off. A month at 80% over forty backtested calls and a month at 80%
 * over forty live ones are not the same evidence.
 */

import { lastTwelveMonths, monthLabel, rate } from "@/lib/progress";
import type { MonthRecord } from "@/lib/progress";

export function MonthlyTable({ months }: { months: MonthRecord[] }) {
  const window = lastTwelveMonths(months);
  if (window.every((row) => row.record === null)) return null;

  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] p-5">
      <h2 className="text-[15px] font-semibold">Monthly breakdown</h2>
      <p className="mt-1.5 max-w-[68ch] text-[13px] leading-relaxed text-[var(--color-text-dim)]">
        Each rate beside the number of calls it is measured over, and how many
        of those were stored before kick-off.
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[420px] text-[13px]">
          <thead>
            <tr className="text-left text-[11px] tracking-wider text-[var(--color-text-faint)] uppercase">
              <th className="pb-2 font-medium">Month</th>
              <th className="pb-2 text-right font-medium">Win rate</th>
              <th className="pb-2 text-right font-medium">Settled</th>
              <th className="pb-2 text-right font-medium">Live</th>
            </tr>
          </thead>
          <tbody>
            {[...window].reverse().map(({ month, record }) => (
              <tr key={month} className="border-t border-[var(--color-line)]">
                <td className="py-2 text-[var(--color-text-dim)]">
                  {monthLabel(month)}
                </td>
                {record && record.settled > 0 ? (
                  <>
                    <td
                      className="py-2 text-right font-semibold tabular-nums"
                      style={{ color: "var(--color-gold-bright)" }}
                    >
                      {rate(record)}
                    </td>
                    <td className="py-2 text-right tabular-nums">
                      {record.settled.toLocaleString()}
                    </td>
                    <td className="py-2 text-right tabular-nums text-[var(--color-text-faint)]">
                      {record.live_settled.toLocaleString()}
                    </td>
                  </>
                ) : (
                  <td
                    colSpan={3}
                    className="py-2 text-right text-[var(--color-text-faint)]"
                  >
                    no settled calls
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
