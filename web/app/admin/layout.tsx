import type { Metadata } from "next";
import Link from "next/link";
import { requireAdmin } from "@/lib/session";

export const metadata: Metadata = {
  title: "Admin",
  robots: { index: false, follow: false },
};

// Every admin page shows live data for one signed-in administrator.
export const dynamic = "force-dynamic";

const LINKS = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/picks", label: "Picks" },
  { href: "/admin/posts", label: "Blog" },
  { href: "/admin/members", label: "Members" },
  { href: "/admin/premium", label: "Premium plans" },
  { href: "/admin/mail", label: "Mail" },
  { href: "/admin/audit", label: "Audit log" },
];

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAdmin("/admin");
  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-8 sm:px-6 lg:px-10">
      <nav
        aria-label="Admin"
        className="flex flex-wrap items-center gap-1 border-b border-[var(--color-line)] pb-3"
      >
        <span className="mr-2 rounded bg-[var(--color-gold)] px-2 py-1 text-[11px] font-extrabold tracking-wider text-[var(--color-ink-on-accent)] uppercase">
          Admin
        </span>
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className="rounded-md px-3 py-1.5 text-[13.5px] font-semibold text-[var(--color-text-dim)] transition-colors hover:bg-[var(--color-surface-raised)] hover:text-[var(--color-text)]"
          >
            {link.label}
          </Link>
        ))}
      </nav>
      <div className="pt-8">{children}</div>
    </div>
  );
}
