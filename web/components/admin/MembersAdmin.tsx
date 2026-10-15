"use client";

import { useState } from "react";
import { Message, inputClass } from "@/components/auth/ui";
import { useAdminData } from "@/components/admin/useAdminData";
import { api } from "@/lib/clientApi";
import type { Entitlement, Member } from "@/lib/session";

type Row = Member & { entitlement: Entitlement };

function until(iso: string | null): string {
  if (!iso) return "";
  return new Date(`${iso}Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function MembersAdmin() {
  const [query, setQuery] = useState("");
  const [applied, setApplied] = useState("");
  const { data, error, loading, reload } = useAdminData<{ users: Row[] }>(
    `admin/users?limit=100&q=${encodeURIComponent(applied)}`,
  );
  const [message, setMessage] = useState<{ tone: "error" | "success"; text: string } | null>(
    null,
  );

  async function run(label: string, path: string, options: { method?: string; body?: unknown } = {}) {
    setMessage(null);
    const result = await api(`/api/engine/${path}`, {
      method: options.method ?? "POST",
      body: options.method === "DELETE" ? undefined : (options.body ?? {}),
    });
    if (result.ok) {
      setMessage({ tone: "success", text: label });
      await reload();
    } else {
      setMessage({
        tone: "error",
        text: result.error?.message ?? "That did not work.",
      });
    }
  }

  function grant(row: Row) {
    const entered = window.prompt(
      `Give ${row.email} premium for how many days?`,
      "30",
    );
    const days = Number(entered);
    if (!entered || !Number.isInteger(days) || days < 1) return;
    void run(`Gave ${row.email} ${days} days of premium.`, `admin/users/${row.id}/grant`, {
      body: { days, note: "Granted from the dashboard" },
    });
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[28px] font-black tracking-[-0.02em]">Members</h1>
        <p className="mt-1 text-[14.5px] text-[var(--color-text-dim)]">
          Find a member, give or end premium, or remove an account.
        </p>
      </header>

      <form
        className="flex gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          setApplied(query.trim());
        }}
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by e-mail"
          aria-label="Search members by e-mail"
          className={`${inputClass} max-w-[360px]`}
        />
        <button type="submit" className="nt-cta nt-cta--ghost">
          Search
        </button>
      </form>

      {message && <Message tone={message.tone}>{message.text}</Message>}
      {loading && <p className="text-[14px] text-[var(--color-text-dim)]">Loading…</p>}
      {error && <Message tone="error">{error}</Message>}
      {data && data.users.length === 0 && (
        <p className="text-[14px] text-[var(--color-text-dim)]">No members found.</p>
      )}

      <ul className="space-y-3">
        {data?.users.map((row) => (
          <li
            key={row.id}
            className="rounded-[12px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-[15.5px] font-bold">{row.email}</p>
                <p className="mt-0.5 text-[12.5px] text-[var(--color-text-dim)]">
                  {row.role === "admin" ? "Administrator" : "Member"} ·{" "}
                  {row.email_verified ? "address confirmed" : "address NOT confirmed"}
                  {row.display_name ? ` · ${row.display_name}` : ""}
                </p>
              </div>
              <p className="text-right text-[12.5px]">
                {row.entitlement.premium ? (
                  <span className="rounded bg-[var(--color-gold)] px-1.5 py-0.5 text-[10px] font-extrabold tracking-wider text-[var(--color-ink-on-accent)] uppercase">
                    Premium{row.entitlement.until ? ` to ${until(row.entitlement.until)}` : ""}
                  </span>
                ) : (
                  <span className="text-[var(--color-text-faint)]">Free</span>
                )}
              </p>
            </div>
            {row.role !== "admin" && (
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="nt-cta nt-cta--primary !px-3 !py-1.5 text-[12px]"
                  onClick={() => grant(row)}
                >
                  Give premium
                </button>
                {row.entitlement.premium && (
                  <button
                    type="button"
                    className="nt-cta nt-cta--ghost !px-3 !py-1.5 text-[12px]"
                    onClick={() => {
                      if (window.confirm(`End premium for ${row.email} now?`)) {
                        void run("Premium ended.", `admin/users/${row.id}/revoke`);
                      }
                    }}
                  >
                    End premium
                  </button>
                )}
                <button
                  type="button"
                  className="nt-cta !px-3 !py-1.5 text-[12px] border-[var(--color-lost)] text-[var(--color-lost)] hover:bg-[var(--color-lost)]/10"
                  onClick={() => {
                    if (
                      window.confirm(
                        `Permanently delete the account ${row.email}? This cannot be undone.`,
                      )
                    ) {
                      void run("Account deleted.", `admin/users/${row.id}`, {
                        method: "DELETE",
                      });
                    }
                  }}
                >
                  Delete account
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
