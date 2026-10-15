/**
 * The small form pieces the account and admin screens share, so every form reads and behaves the
 * same: a labelled field, a message line, and a button that says it is working.
 */

"use client";

import type { InputHTMLAttributes, ReactNode } from "react";

export const inputClass =
  "w-full rounded-[var(--radius-md)] border border-[var(--color-line-strong)] bg-[var(--color-surface)] px-3.5 py-2.5 text-[15px] text-[var(--color-text)] placeholder:text-[var(--color-text-faint)] focus:border-[var(--color-gold)] focus:outline-none";

export function Field({
  label,
  hint,
  id,
  ...input
}: {
  label: string;
  hint?: string;
  id: string;
} & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      <label htmlFor={id} className="text-[13px] font-semibold">
        {label}
      </label>
      <input id={id} className={`${inputClass} mt-1.5`} {...input} />
      {hint && (
        <p className="mt-1 text-[12px] text-[var(--color-text-faint)]">{hint}</p>
      )}
    </div>
  );
}

export function Check({
  id,
  children,
  ...input
}: { id: string; children: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label
      htmlFor={id}
      className="flex items-start gap-3 text-[13.5px] leading-snug text-[var(--color-text-dim)]"
    >
      <input
        id={id}
        type="checkbox"
        className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-gold)]"
        {...input}
      />
      <span>{children}</span>
    </label>
  );
}

export function Message({
  tone,
  children,
}: {
  tone: "error" | "success" | "info";
  children: ReactNode;
}) {
  const style =
    tone === "error"
      ? "border-[var(--color-lost)]/50 bg-[var(--color-lost)]/10 text-[var(--color-text)]"
      : tone === "success"
        ? "border-[var(--color-won)]/50 bg-[var(--color-won)]/10 text-[var(--color-text)]"
        : "border-[var(--color-line-strong)] bg-[var(--color-surface-raised)] text-[var(--color-text-dim)]";
  return (
    <p
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-[var(--radius-md)] border px-3.5 py-2.5 text-[13.5px] leading-snug ${style}`}
    >
      {children}
    </p>
  );
}

export function SubmitButton({
  busy,
  children,
  danger = false,
}: {
  busy: boolean;
  children: ReactNode;
  danger?: boolean;
}) {
  return (
    <button
      type="submit"
      disabled={busy}
      className={`nt-cta w-full disabled:cursor-wait disabled:opacity-60 ${
        danger
          ? "border-[var(--color-lost)] text-[var(--color-lost)] hover:bg-[var(--color-lost)]/10"
          : "nt-cta--primary"
      }`}
    >
      {busy ? "Please wait…" : children}
    </button>
  );
}

export function PanelCard({
  title,
  intro,
  children,
}: {
  title: string;
  intro?: string;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto w-full max-w-[460px] px-4 py-14 sm:py-20">
      <h1 className="text-[clamp(1.7rem,4vw,2.2rem)] leading-tight font-black tracking-[-0.02em]">
        {title}
      </h1>
      {intro && (
        <p className="mt-2 text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
          {intro}
        </p>
      )}
      <div className="mt-6 rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-5 sm:p-6">
        {children}
      </div>
    </div>
  );
}
