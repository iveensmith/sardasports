"use client";

import { useState } from "react";
import { Message } from "@/components/auth/ui";
import { api } from "@/lib/clientApi";

export function CheckoutButton({
  planCode,
  label,
  provider,
}: {
  planCode: string;
  label: string;
  provider?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    const result = await api<{ url: string }>("/api/engine/premium/checkout", {
      body: { plan_code: planCode, provider },
    });
    if (result.ok && result.data?.url) {
      // The member pays on the provider's own page; card details never touch this site.
      window.location.assign(result.data.url);
      return;
    }
    setBusy(false);
    setError(result.error?.message ?? "Could not start the payment.");
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={start}
        disabled={busy}
        className="nt-cta nt-cta--primary w-full disabled:cursor-wait disabled:opacity-60"
      >
        {busy ? "Opening the payment page…" : label}
      </button>
      {error && <Message tone="error">{error}</Message>}
    </div>
  );
}
