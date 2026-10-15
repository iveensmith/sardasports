import { PanelCard } from "@/components/auth/ui";
import { ResetPasswordForm } from "@/components/auth/RecoveryForms";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
  title: "Choose a new password",
  description: "Choose a new SARDASPORTS password.",
  path: "/reset-password",
  noindex: true,
});

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  return (
    <PanelCard title="Choose a new password">
      <ResetPasswordForm token={token ?? null} />
    </PanelCard>
  );
}
