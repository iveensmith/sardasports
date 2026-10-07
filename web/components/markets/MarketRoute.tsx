/**
 * Loads one market page and renders it, or says plainly that the engine could
 * not be reached. Shared by the two single-market routes so they cannot drift
 * apart in how they fail.
 */

import { EngineError, getMarketPage } from "@/lib/api";
import type { MarketKind, MarketPageData } from "@/lib/markets";
import { MarketPage, type MarketCopy } from "@/components/markets/MarketPage";

export async function MarketRoute({
  kind,
  copy,
  searchParams,
}: {
  kind: MarketKind;
  copy: MarketCopy;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const raw = params.date;
  const date = (Array.isArray(raw) ? raw[0] : raw) ?? "";

  let data: MarketPageData | null = null;
  let error: string | null = null;
  try {
    data = await getMarketPage(kind, date || undefined);
  } catch (e) {
    error =
      e instanceof EngineError || e instanceof Error
        ? e.message
        : "The engine could not be reached.";
  }

  if (error || !data) {
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

  return <MarketPage data={data} copy={copy} />;
}
