import { PanelCard } from "@/components/auth/ui";
import { SignUpForm } from "@/components/auth/SignUpForm";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
  title: "Create an account",
  description:
    "Create a free SARDASPORTS account and unlock premium if you want it. 18+ only.",
  path: "/signup",
  noindex: true,
});

export default function SignUpPage() {
  return (
    <PanelCard
      title="Create your account"
      intro="Free, and optional: every board and the record stay open to everyone. An account is where premium lives and where your e-mail preferences are kept."
    >
      <SignUpForm />
    </PanelCard>
  );
}
