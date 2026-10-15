import { PanelCard } from "@/components/auth/ui";
import { LoginForm } from "@/components/auth/LoginForm";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
  title: "Log in",
  description: "Log in to your SARDASPORTS account.",
  path: "/login",
  noindex: true,
});

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;
  return (
    <PanelCard title="Log in">
      <LoginForm next={next ?? null} />
    </PanelCard>
  );
}
