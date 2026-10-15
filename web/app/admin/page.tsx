import Link from "next/link";
import type { PicksRecord, PlanView } from "@/lib/content";
import { engineCall, sessionToken } from "@/lib/session";

interface Overview {
  users: number;
  verified_users: number;
  premium_members: number;
  posts_published: number;
  posts_draft: number;
  picks: PicksRecord;
  mail_configured: boolean;
  mail_unsent: number;
}

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-[12px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-4">
      <p className="text-[11px] font-extrabold tracking-[0.12em] text-[var(--color-text-dim)] uppercase">
        {label}
      </p>
      <p className="mt-1.5 text-[28px] leading-none font-black tabular-nums">
        {value}
      </p>
      {note && (
        <p className="mt-1.5 text-[12.5px] text-[var(--color-text-faint)]">{note}</p>
      )}
    </div>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <li className="rounded-[var(--radius-md)] border border-[var(--color-gold)]/50 bg-[var(--color-gold)]/[0.07] px-4 py-3 text-[14px] leading-snug">
      {children}
    </li>
  );
}

export default async function AdminOverview() {
  const token = await sessionToken();
  const [overview, plans] = await Promise.all([
    engineCall<Overview>("/admin/overview", { token }),
    engineCall<{ plans: PlanView[]; providers: string[] }>("/premium/plans"),
  ]);
  const o = overview.data;
  const notices: React.ReactNode[] = [];
  if (o && !o.mail_configured) {
    notices.push(
      <Notice key="mail">
        <b>No mail server is set up.</b> Confirmation and reset e-mails are
        written to the{" "}
        <Link href="/admin/mail" className="underline underline-offset-4">
          mail outbox
        </Link>{" "}
        and not sent, so new members cannot confirm their address until you
        add SMTP details (or pass the link on by hand from there).
      </Notice>,
    );
  }
  if (plans.data && plans.data.plans.length === 0) {
    notices.push(
      <Notice key="plans">
        No premium plan is switched on.{" "}
        <Link href="/admin/premium" className="underline underline-offset-4">
          Create one
        </Link>{" "}
        when you have decided the price.
      </Notice>,
    );
  }
  if (plans.data && plans.data.providers.length === 0) {
    notices.push(
      <Notice key="providers">
        No payment provider is configured, so members cannot pay online yet. You
        can still grant premium by hand from{" "}
        <Link href="/admin/members" className="underline underline-offset-4">
          Members
        </Link>
        .
      </Notice>,
    );
  }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-[28px] font-black tracking-[-0.02em]">Overview</h1>
        <p className="mt-1 text-[14.5px] text-[var(--color-text-dim)]">
          What is on the site and who is using it.
        </p>
      </header>

      {notices.length > 0 && <ul className="space-y-3">{notices}</ul>}

      {!o ? (
        <p className="text-[14.5px] text-[var(--color-text-dim)]">
          The overview could not be loaded: the engine did not answer.
        </p>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Tile label="Members" value={String(o.users)} note={`${o.verified_users} confirmed`} />
            <Tile label="Premium now" value={String(o.premium_members)} />
            <Tile
              label="Posts"
              value={String(o.posts_published)}
              note={`${o.posts_draft} draft`}
            />
            <Tile
              label="Editor's picks"
              value={String(o.picks.published)}
              note={
                o.picks.win_rate === null
                  ? `${o.picks.pending} to play`
                  : `${o.picks.won}-${o.picks.lost}, ${o.picks.win_rate}% won`
              }
            />
          </section>

          <section className="grid gap-3 sm:grid-cols-3">
            <Link
              href="/admin/picks"
              className="nt-cta nt-cta--primary"
            >
              Write a pick
            </Link>
            <Link href="/admin/posts/new" className="nt-cta nt-cta--ghost">
              Write a blog post
            </Link>
            <Link href="/admin/members" className="nt-cta nt-cta--ghost">
              Manage members
            </Link>
          </section>
        </>
      )}
    </div>
  );
}
