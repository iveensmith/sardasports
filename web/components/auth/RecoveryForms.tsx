"use client";

/**
 * The three small flows that arrive by e-mail link or lead to one: ask for a reset, set a new
 * password from the link, confirm an address from the link.
 */

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Field, Message, SubmitButton } from "@/components/auth/ui";
import { api } from "@/lib/clientApi";

export function ForgotPasswordForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    const result = await api("/api/auth/forgot-password", {
      body: { email: String(form.get("email") ?? "") },
    });
    setBusy(false);
    if (result.ok) setSent(true);
    else setError(result.error?.message ?? "Could not send the link.");
  }

  if (sent) {
    return (
      <Message tone="success">
        If that address has an account, a link to choose a new password is on
        its way. It works for one hour.
      </Message>
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
      {error && <Message tone="error">{error}</Message>}
      <SubmitButton busy={busy}>Send the reset link</SubmitButton>
    </form>
  );
}

export function ResetPasswordForm({ token }: { token: string | null }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (form.get("password") !== form.get("again")) {
      setError("The two passwords are not the same.");
      return;
    }
    setBusy(true);
    setError(null);
    const result = await api("/api/auth/reset-password", {
      body: { token, password: String(form.get("password") ?? "") },
    });
    setBusy(false);
    if (result.ok) setDone(true);
    else setError(result.error?.message ?? "Could not change the password.");
  }

  if (!token) {
    return (
      <Message tone="error">
        This page needs the link from your e-mail.{" "}
        <Link href="/forgot-password" className="underline">
          Ask for a new one
        </Link>
        .
      </Message>
    );
  }
  if (done) {
    return (
      <div className="space-y-3">
        <Message tone="success">
          Your password has been changed and you have been signed out
          everywhere.
        </Message>
        <Link
          href="/login"
          className="inline-block text-[14px] font-semibold text-[var(--color-gold-bright)] underline underline-offset-4"
        >
          Log in
        </Link>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <Field
        id="password"
        name="password"
        type="password"
        label="New password"
        autoComplete="new-password"
        minLength={10}
        required
        hint="At least 10 characters."
      />
      <Field
        id="again"
        name="again"
        type="password"
        label="Type it again"
        autoComplete="new-password"
        required
      />
      {error && <Message tone="error">{error}</Message>}
      <SubmitButton busy={busy}>Set the new password</SubmitButton>
    </form>
  );
}

export function VerifyEmail({ token }: { token: string | null }) {
  const [state, setState] = useState<"working" | "ok" | "error">(
    token ? "working" : "error",
  );
  const [message, setMessage] = useState(
    token ? "" : "This page needs the link from your e-mail.",
  );
  // A confirmation link is single-use: StrictMode runs effects twice in development, and a second
  // call would report the link as already used, so the request is made once per page.
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    api("/api/auth/verify-email", { body: { token } }).then((result) => {
      if (result.ok) setState("ok");
      else {
        setState("error");
        setMessage(
          result.error?.message ?? "This link is invalid or has expired.",
        );
      }
    });
  }, [token]);

  if (state === "working") {
    return <Message tone="info">Confirming your address…</Message>;
  }
  if (state === "ok") {
    return (
      <div className="space-y-3">
        <Message tone="success">
          Your e-mail address is confirmed. Your account is ready.
        </Message>
        <Link href="/login" className="nt-cta nt-cta--primary w-full">
          Log in
        </Link>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <Message tone="error">{message}</Message>
      <Link
        href="/login"
        className="inline-block text-[14px] font-semibold text-[var(--color-gold-bright)] underline underline-offset-4"
      >
        Log in to ask for a new link
      </Link>
    </div>
  );
}
