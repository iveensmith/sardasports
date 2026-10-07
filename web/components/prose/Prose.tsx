/**
 * Building blocks for the long-form pages (About, Contact, Privacy).
 *
 * Kept deliberately plain: one reading column, headings that nest properly, a
 * comfortable line length, and links that look like links. These pages are read,
 * not scanned, so there is nothing here to compete with the words.
 */

import type { ReactNode } from "react";

export function PageHeader({
  title,
  intro,
}: {
  title: string;
  intro?: ReactNode;
}) {
  return (
    <header className="max-w-[72ch]">
      <h1 className="text-[clamp(1.9rem,4.5vw,2.75rem)] leading-tight font-bold tracking-[-0.02em]">
        {title}
      </h1>
      {intro && (
        <p className="mt-4 text-[16px] leading-relaxed text-[var(--color-text-dim)]">
          {intro}
        </p>
      )}
    </header>
  );
}

export function Section({
  id,
  title,
  children,
}: {
  id?: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className="max-w-[72ch] scroll-mt-24 border-t border-[var(--color-line)] pt-9"
    >
      <h2 className="text-[21px] font-bold tracking-[-0.015em]">{title}</h2>
      <div className="mt-3 space-y-4 text-[15px] leading-relaxed text-[var(--color-text-dim)]">
        {children}
      </div>
    </section>
  );
}

export function List({ children }: { children: ReactNode }) {
  return (
    <ul className="list-disc space-y-2 pl-5 marker:text-[var(--color-text-faint)]">
      {children}
    </ul>
  );
}

export function Strong({ children }: { children: ReactNode }) {
  return (
    <strong className="font-semibold text-[var(--color-text)]">
      {children}
    </strong>
  );
}

export const linkClass =
  "text-[var(--color-gold-bright)] underline underline-offset-4 decoration-[var(--color-line-strong)] hover:decoration-[var(--color-gold-bright)]";
