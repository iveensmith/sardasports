/**
 * What a page shows in the moments between a click and its content.
 *
 * Next.js shows a route's `loading.tsx` the instant a navigation starts and swaps in the real
 * page when it is ready, so a click always answers at once even when the page behind it needs
 * the engine. Two shapes: `board` (a heading, a day strip and rows of fixtures; used by the
 * match, basketball, tennis and live pages) and `article` (a heading and some text; everything
 * else).
 *
 * Nothing is drawn for the first 150 ms (see `.sk` in globals.css): most clicks finish inside
 * that, and a skeleton that flashes for a few frames and vanishes looks like a glitch, not help.
 * It is plain blocks of the page's own surface colour, not figures: no number or name appears
 * here that the real page might not show.
 */

function Bar({ className = "" }: { className?: string }) {
  return <span aria-hidden className={`sk-bar block ${className}`} />;
}

export function PageSkeleton({
  variant = "article",
  label = "Loading the page",
}: {
  variant?: "article" | "board";
  label?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className="sk mx-auto w-full max-w-[1200px] px-4 py-10 sm:px-6 sm:py-12 lg:px-10"
    >
      <span className="sr-only">{label}</span>

      <Bar className="h-9 w-3/4 max-w-[520px] sm:h-11" />
      <Bar className="mt-4 h-4 w-full max-w-[640px]" />
      <Bar className="mt-2 h-4 w-2/3 max-w-[460px]" />

      {variant === "board" ? (
        <>
          <div className="mt-8 flex gap-2 overflow-hidden" aria-hidden>
            {Array.from({ length: 7 }, (_, i) => (
              <Bar key={i} className="h-10 w-20 shrink-0 rounded-full" />
            ))}
          </div>
          <div className="mt-6 space-y-2.5" aria-hidden>
            {Array.from({ length: 8 }, (_, i) => (
              <div
                key={i}
                className="flex items-center gap-4 rounded-[12px] border border-[var(--color-line)] bg-[var(--color-surface)] p-4"
              >
                <Bar className="h-9 w-9 shrink-0 rounded-full" />
                <div className="min-w-0 flex-1 space-y-2">
                  <Bar className="h-4 w-1/2 max-w-[260px]" />
                  <Bar className="h-3 w-1/3 max-w-[160px]" />
                </div>
                <Bar className="hidden h-8 w-16 shrink-0 sm:block" />
                <Bar className="h-8 w-16 shrink-0" />
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="mt-10 space-y-4" aria-hidden>
          {Array.from({ length: 3 }, (_, i) => (
            <div
              key={i}
              className="rounded-[14px] border border-[var(--color-line)] bg-[var(--color-surface)] p-5"
            >
              <Bar className="h-5 w-1/3 max-w-[240px]" />
              <Bar className="mt-4 h-3.5 w-full" />
              <Bar className="mt-2 h-3.5 w-11/12" />
              <Bar className="mt-2 h-3.5 w-4/6" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
