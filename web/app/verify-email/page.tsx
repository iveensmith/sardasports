import { PanelCard } from "@/components/auth/ui";
import { VerifyEmail } from "@/components/auth/RecoveryForms";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
  title: "Confirm your e-mail address",
  description: "Confirm your e-mail address to finish creating your account.",
  path: "/verify-email",
  noindex: true,
});

export default async function VerifyEmailPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  return (
    <PanelCard title="Confirm your e-mail address">
      <VerifyEmail token={token ?? null} />
    </PanelCard>
  );
}
