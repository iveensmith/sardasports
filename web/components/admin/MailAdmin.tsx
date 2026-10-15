"use client";

import { useState } from "react";
import { Message } from "@/components/auth/ui";
import { useAdminData } from "@/components/admin/useAdminData";

interface Mail {
  id: number;
  created_at: string | null;
  to: string;
  subject: string;
  body: string;
  kind: string;
  sent: boolean;
  attempts: number;
  error: string | null;
}

export function MailAdmin() {
  const { data, error, loading } = useAdminData<{
    mail_configured: boolean;
    messages: Mail[];
  }>("admin/outbox?limit=100");
  const [open, setOpen] = useState<number | null>(null);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[28px] font-black tracking-[-0.02em]">Mail outbox</h1>
        <p className="mt-1 max-w-[70ch] text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
          Every e-mail the site writes (confirmations, password resets, account
          notices) is kept here first.
        </p>
      </header>

      {data && !data.mail_configured && (
        <Message tone="info">
          No mail server is set up, so these messages are <b>not sent</b>. To
          send them, add the SMTP settings in the server&rsquo;s environment
          (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM). Until
          then you can open a message and pass its link to the member.
        </Message>
      )}
      {loading && <p className="text-[14px] text-[var(--color-text-dim)]">Loading…</p>}
      {error && <Message tone="error">{error}</Message>}
      {data && data.messages.length === 0 && (
        <p className="text-[14px] text-[var(--color-text-dim)]">Nothing written yet.</p>
      )}

      <ul className="space-y-2">
        {data?.messages.map((mail) => (
          <li
            key={mail.id}
            className="rounded-[12px] border border-[var(--color-line-strong)] bg-[var(--color-surface)]"
          >
            <button
              type="button"
              onClick={() => setOpen(open === mail.id ? null : mail.id)}
              className="flex w-full flex-wrap items-center justify-between gap-2 p-4 text-left"
              aria-expanded={open === mail.id}
            >
              <span className="min-w-0">
                <span className="block truncate text-[14.5px] font-semibold">
                  {mail.subject}
                </span>
                <span className="block truncate text-[12.5px] text-[var(--color-text-dim)]">
                  To {mail.to}
                </span>
              </span>
              <span
                className={`rounded px-2 py-0.5 text-[10.5px] font-extrabold tracking-wider uppercase ${
                  mail.sent
                    ? "bg-[var(--color-won)]/20 text-[var(--color-won)]"
                    : "bg-[var(--color-surface-raised)] text-[var(--color-text-dim)]"
                }`}
              >
                {mail.sent ? "Sent" : "Not sent"}
              </span>
            </button>
            {open === mail.id && (
              <div className="border-t border-[var(--color-line)] p-4">
                <pre className="overflow-x-auto text-[13px] leading-relaxed whitespace-pre-wrap">
                  {mail.body}
                </pre>
                {mail.error && (
                  <p className="mt-3 text-[12.5px] text-[var(--color-lost)]">
                    Last error: {mail.error}
                  </p>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
