import { engineCall, sessionToken } from "@/lib/session";

interface Entry {
  id: number;
  at: string | null;
  actor_id: number | null;
  action: string;
  target: string | null;
  detail: string | null;
}

export default async function AuditPage() {
  const token = await sessionToken();
  const { data } = await engineCall<{ entries: Entry[] }>(
    "/admin/audit?limit=200",
    { token },
  );
  const entries = data?.entries ?? [];
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[28px] font-black tracking-[-0.02em]">Audit log</h1>
        <p className="mt-1 text-[14.5px] text-[var(--color-text-dim)]">
          Every change to posts, picks, plans and members, newest first.
        </p>
      </header>
      {entries.length === 0 ? (
        <p className="text-[14px] text-[var(--color-text-dim)]">Nothing recorded yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-[12px] border border-[var(--color-line-strong)]">
          <table className="w-full min-w-[640px] text-left text-[13.5px]">
            <thead className="bg-[var(--color-surface)] text-[12px] tracking-wider text-[var(--color-text-dim)] uppercase">
              <tr>
                <th className="px-3 py-2.5 font-semibold">When (UTC)</th>
                <th className="px-3 py-2.5 font-semibold">Action</th>
                <th className="px-3 py-2.5 font-semibold">Target</th>
                <th className="px-3 py-2.5 font-semibold">Detail</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id} className="border-t border-[var(--color-line)]">
                  <td className="px-3 py-2 whitespace-nowrap tabular-nums text-[var(--color-text-dim)]">
                    {entry.at?.replace("T", " ").slice(0, 16)}
                  </td>
                  <td className="px-3 py-2 font-semibold">{entry.action}</td>
                  <td className="px-3 py-2 text-[var(--color-text-dim)]">{entry.target}</td>
                  <td className="px-3 py-2 text-[var(--color-text-dim)]">{entry.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
