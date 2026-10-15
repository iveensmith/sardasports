import { redirect } from "next/navigation";
import { AccountPanel } from "@/components/auth/AccountPanel";
import { getSession } from "@/lib/session";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
  title: "Your account",
  description: "Manage your SARDASPORTS account.",
  path: "/account",
  noindex: true,
});

// Per request: it shows the signed-in member, so it can never be a shared, cached page.
export const dynamic = "force-dynamic";

export default async function AccountPage({
  searchParams,
}: {
  searchParams: Promise<{ premium?: string }>;
}) {
  const session = await getSession();
  if (!session) redirect("/login?next=/account");
  const { premium } = await searchParams;
  return (
    <AccountPanel
      user={session.user}
      entitlement={session.entitlement}
      thanks={premium === "thanks"}
    />
  );
}
