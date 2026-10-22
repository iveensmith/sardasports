"use client";

/**
 * The signed-in member's own page: who they are, whether premium is on, and the three things
 * they must always be able to do themselves: change the password, sign out everywhere, and delete
 * the account.
 */

import Link from "next/link";
import { useState } from "react";
import {
  Check,
  Field,
  Message,
  PasswordInput,
  SubmitButton,
  inputClass,
} from "@/components/auth/ui";
import { api } from "@/lib/clientApi";
import type { Entitlement, Member } from "@/lib/session";

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-5 sm:p-6">
      <h2 className="text-[17px] font-bold">{title}</h2>
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  );
}

function dateLabel(iso: string | null): string {
  if (!iso) return "";
  return new Date(`${iso}${iso.endsWith("Z") ? "" : "Z"}`).toLocaleDateString(
    "en-GB",
    { day: "numeric", month: "long", year: "numeric" },
  );
}

export function AccountPanel({
  user,
  entitlement,
  thanks,
}: {
  user: Member;
  entitlement: Entitlement;
  thanks: boolean;
}) {
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [passwordMessage, setPasswordMessage] = useState<{
    tone: "error" | "success";
    text: string;
  } | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy("profile");
    const result = await api("/api/auth/profile", {
      method: "PATCH",
      body: {
        display_name: String(form.get("name") ?? ""),
        marketing_opt_in: form.get("marketing") === "on",
      },
    });
    setBusy(null);
    setProfileMessage(
      result.ok ? "Saved." : (result.error?.message ?? "Could not save."),
    );
  }

  async function changePassword(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setBusy("password");
    const result = await api("/api/auth/change-password", {
      body: {
        current_password: String(form.get("current") ?? ""),
        new_password: String(form.get("next") ?? ""),
      },
    });
    setBusy(null);
    if (result.ok) {
      formElement.reset();
      setPasswordMessage({ tone: "success", text: "Your password was changed." });
    } else {
      setPasswordMessage({
        tone: "error",
        text: result.error?.message ?? "Could not change the password.",
      });
    }
  }

  async function signOut(everywhere: boolean) {
    setBusy("signout");
    await api(everywhere ? "/api/auth/logout-all" : "/api/auth/logout", {
      body: {},
    });
    // A full navigation, on purpose: the signed-out state has to reach every cached page.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/");
  }

  async function deleteAccount(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy("delete");
    setDeleteError(null);
    const result = await api("/api/auth/delete-account", {
      body: { password: String(form.get("password") ?? "") },
    });
    if (result.ok) {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/?account=deleted");
      return;
    }
    setBusy(null);
    setDeleteError(result.error?.message ?? "Could not delete the account.");
  }

  return (
    <div className="mx-auto w-full max-w-[760px] space-y-5 px-4 py-12 sm:py-16">
      <header>
        <h1 className="text-[clamp(1.8rem,4vw,2.4rem)] leading-tight font-black tracking-[-0.02em]">
          Your account
        </h1>
        <p className="mt-1 text-[14.5px] text-[var(--color-text-dim)]">
          Signed in as <b className="text-[var(--color-text)]">{user.email}</b>
        </p>
      </header>

      {thanks && (
        <Message tone="success">
          Thank you. Your payment is being confirmed; premium switches on as
          soon as the payment provider tells us it went through, usually within
          a minute. Refresh this page if it has not yet.
        </Message>
      )}

      {user.role === "admin" && (
        <Section title="Administrator">
          <Link href="/admin" className="nt-cta nt-cta--primary">
            Open the admin dashboard
          </Link>
        </Section>
      )}

      <Section title="Premium">
        {entitlement.premium ? (
          <div className="space-y-2">
            <p className="text-[15px]">
              <span className="rounded bg-[var(--color-gold)] px-2 py-0.5 text-[11px] font-extrabold tracking-wider text-[var(--color-ink-on-accent)] uppercase">
                Active
              </span>{" "}
              {entitlement.until
                ? `Your premium access runs until ${dateLabel(entitlement.until)}.`
                : "You have premium access as an administrator."}
            </p>
            {entitlement.cancel_at_period_end && (
              <p className="text-[13.5px] text-[var(--color-text-dim)]">
                It will not renew by itself; it simply ends on that date.
              </p>
            )}
            <Link
              href="/premium"
              className="inline-block text-[14px] font-semibold text-[var(--color-gold-bright)] underline underline-offset-4"
            >
              Extend premium
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-[14.5px] text-[var(--color-text-dim)]">
              You are on the free plan: 15 predictions a day and the record
              stay free. Premium opens the rest before kick-off.
            </p>
            <Link href="/premium" className="nt-cta nt-cta--primary">
              See premium
            </Link>
          </div>
        )}
      </Section>

      <Section title="Profile">
        <form onSubmit={saveProfile} className="space-y-4">
          <Field
            id="name"
            name="name"
            label="Name"
            defaultValue={user.display_name ?? ""}
            maxLength={80}
          />
          <Check id="marketing" name="marketing" defaultChecked={user.marketing_opt_in}>
            E-mail me occasional news about the site, such as new features and
            premium offers. Off unless you tick it, and you can turn it off at
            any time.
          </Check>
          {profileMessage && <Message tone="info">{profileMessage}</Message>}
          <SubmitButton busy={busy === "profile"}>Save</SubmitButton>
        </form>
      </Section>

      <Section title="Change your password">
        <form onSubmit={changePassword} className="space-y-4">
          <Field
            id="current"
            name="current"
            type="password"
            label="Current password"
            autoComplete="current-password"
            required
          />
          <Field
            id="next"
            name="next"
            type="password"
            label="New password"
            autoComplete="new-password"
            minLength={10}
            required
            hint="At least 10 characters."
          />
          {passwordMessage && (
            <Message tone={passwordMessage.tone}>{passwordMessage.text}</Message>
          )}
          <SubmitButton busy={busy === "password"}>Change password</SubmitButton>
        </form>
      </Section>

      <Section title="Sign out">
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => signOut(false)}
            disabled={busy === "signout"}
            className="nt-cta nt-cta--ghost"
          >
            Sign out
          </button>
          <button
            type="button"
            onClick={() => signOut(true)}
            disabled={busy === "signout"}
            className="nt-cta nt-cta--ghost"
          >
            Sign out everywhere
          </button>
        </div>
      </Section>

      <Section title="Delete your account">
        <p className="text-[14px] leading-relaxed text-[var(--color-text-dim)]">
          This permanently deletes your account, your sign-ins and your premium
          access. It cannot be undone. Anything you paid for is not refunded
          automatically; contact us if you have a question about a payment.
        </p>
        {!confirmDelete ? (
          <button
            type="button"
            onClick={() => setConfirmDelete(true)}
            className="nt-cta border-[var(--color-lost)] text-[var(--color-lost)] hover:bg-[var(--color-lost)]/10"
          >
            Delete my account
          </button>
        ) : (
          <form onSubmit={deleteAccount} className="space-y-4">
            <div>
              <label htmlFor="delete-password" className="text-[13px] font-semibold">
                Enter your password to confirm
              </label>
              <div className="mt-1.5">
                <PasswordInput
                  id="delete-password"
                  name="password"
                  autoComplete="current-password"
                  required
                  className={inputClass}
                />
              </div>
            </div>
            {deleteError && <Message tone="error">{deleteError}</Message>}
            <div className="flex flex-wrap gap-3">
              <div className="min-w-[180px] flex-1">
                <SubmitButton busy={busy === "delete"} danger>
                  Permanently delete
                </SubmitButton>
              </div>
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="nt-cta nt-cta--ghost"
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </Section>
    </div>
  );
}
