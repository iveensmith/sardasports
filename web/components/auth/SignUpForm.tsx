"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, Field, Message, SubmitButton } from "@/components/auth/ui";
import { api } from "@/lib/clientApi";

export function SignUpForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ email: string; mailReady: boolean } | null>(
    null,
  );

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    const result = await api<{ mail_configured?: boolean }>(
      "/api/auth/register",
      {
        body: {
          email: String(form.get("email") ?? ""),
          password: String(form.get("password") ?? ""),
          display_name: String(form.get("name") ?? ""),
          over_18: form.get("over18") === "on",
          accept_terms: form.get("terms") === "on",
        },
      },
    );
    setBusy(false);
    if (result.ok) {
      setDone({
        email: String(form.get("email") ?? ""),
        mailReady: result.data?.mail_configured !== false,
      });
    } else {
      setError(result.error?.message ?? "Could not create the account.");
    }
  }

  if (done) {
    return (
      <div className="space-y-3">
        <Message tone="success">
          Almost there. We sent a confirmation link to <b>{done.email}</b>.
          Open it to finish creating your account.
        </Message>
        <p className="text-[13px] leading-relaxed text-[var(--color-text-dim)]">
          It can take a minute to arrive; check the spam folder too. The link
          works for 48 hours.
        </p>
        <Link
          href="/login"
          className="inline-block text-[14px] font-semibold text-[var(--color-gold-bright)] underline underline-offset-4"
        >
          Go to log in
        </Link>
      </div>
    );
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
      />
      <Field
        id="name"
        name="name"
        type="text"
        label="Name (optional)"
        autoComplete="nickname"
        maxLength={80}
      />
      <Field
        id="password"
        name="password"
        type="password"
        label="Password"
        autoComplete="new-password"
        minLength={10}
        required
        hint="At least 10 characters. A few words in a row is easy to remember and hard to guess."
      />
      <div className="space-y-3 pt-1">
        <Check id="over18" name="over18" required>
          I confirm that I am <b>18 years old or over</b>.
        </Check>
        <Check id="terms" name="terms" required>
          I accept the{" "}
          <Link href="/terms" className="underline underline-offset-4">
            Terms of use
          </Link>{" "}
          and have read the{" "}
          <Link href="/privacy" className="underline underline-offset-4">
            Privacy policy
          </Link>
          .
        </Check>
      </div>
      {error && <Message tone="error">{error}</Message>}
      <SubmitButton busy={busy}>Create account</SubmitButton>
      <p className="text-center text-[13.5px] text-[var(--color-text-dim)]">
        Already have an account?{" "}
        <Link
          href="/login"
          className="font-semibold text-[var(--color-gold-bright)] underline underline-offset-4"
        >
          Log in
        </Link>
      </p>
    </form>
  );
}
