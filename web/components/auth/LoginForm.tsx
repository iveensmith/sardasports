"use client";

import Link from "next/link";
import { useState } from "react";
import { Field, Message, SubmitButton } from "@/components/auth/ui";
import { api } from "@/lib/clientApi";

/** Only a path on this site is a safe place to send someone after signing in. */
function safeNext(next: string | null): string {
  if (next && next.startsWith("/") && !next.startsWith("//")) return next;
  return "/account";
}

export function LoginForm({ next }: { next: string | null }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ code: string; message: string } | null>(
    null,
  );
  const [resent, setResent] = useState(false);
  const [email, setEmail] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    setResent(false);
    const result = await api("/api/auth/login", {
      body: {
        email: String(form.get("email") ?? ""),
        password: String(form.get("password") ?? ""),
      },
    });
    if (result.ok) {
      // A full navigation, so the header and every page pick up the new session.
      window.location.assign(safeNext(next));
      return;
    }
    setBusy(false);
    setError(
      result.error ?? { code: "error", message: "Could not log in." },
    );
  }

  async function resend() {
    await api("/api/auth/resend-verification", { body: { email } });
    setResent(true);
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <Field
        id="email"
        name="email"
        type="email"
        label="E-mail address"
        autoComplete="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <Field
        id="password"
        name="password"
        type="password"
        label="Password"
        autoComplete="current-password"
        required
      />
      {error && <Message tone="error">{error.message}</Message>}
      {error?.code === "not_verified" && (
        <div className="space-y-2">
          <button
            type="button"
            onClick={resend}
            className="text-[13.5px] font-semibold text-[var(--color-gold-bright)] underline underline-offset-4"
          >
            Send the confirmation link again
          </button>
          {resent && (
            <Message tone="success">
              If that address has an account, a new link is on its way.
            </Message>
          )}
        </div>
      )}
      <SubmitButton busy={busy}>Log in</SubmitButton>
      <div className="flex flex-wrap items-center justify-between gap-2 text-[13.5px] text-[var(--color-text-dim)]">
        <Link
          href="/forgot-password"
          className="underline underline-offset-4 hover:text-[var(--color-text)]"
        >
          Forgot your password?
        </Link>
        <Link
          href="/signup"
          className="font-semibold text-[var(--color-gold-bright)] underline underline-offset-4"
        >
          Create an account
        </Link>
      </div>
    </form>
  );
}
