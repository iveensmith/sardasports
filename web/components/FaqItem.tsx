/**
 * One question and answer, as a plain `<details>`/`<summary>` rather than a
 * client component with its own open/close state — an accordion is exactly
 * what that element already does, for free, with no JS and working keyboard
 * and screen-reader behaviour out of the box.
 */

export function FaqItem({ q, a }: { q: string; a: string }) {
  return (
    <details className="group rounded-[var(--radius-lg)] border border-[var(--color-line)] bg-[var(--color-surface)] px-5 py-4 open:pb-4">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-[14.5px] font-medium marker:content-none">
        {q}
        <span
          aria-hidden
          className="shrink-0 text-[18px] leading-none text-[var(--color-text-faint)] transition-transform group-open:rotate-45"
        >
          +
        </span>
      </summary>
      <p className="mt-3 text-[13.5px] leading-relaxed text-[var(--color-text-dim)]">
        {a}
      </p>
    </details>
  );
}
