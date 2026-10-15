import { PanelCard } from "@/components/auth/ui";
import { ForgotPasswordForm } from "@/components/auth/RecoveryForms";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
  title: "Reset your password",
  description: "Ask for a link to choose a new SARDASPORTS password.",
  path: "/forgot-password",
  noindex: true,
});

export default function ForgotPasswordPage() {
  return (
    <PanelCard
      title="Reset your password"
      intro="Enter the e-mail address of your account and we will send you a link to choose a new password."
    >
      <ForgotPasswordForm />
    </PanelCard>
  );
}
