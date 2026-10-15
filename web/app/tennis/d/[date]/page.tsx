import { redirect } from "next/navigation";
import { SportRoute } from "@/components/sport/SportRoute";
import { validSportDay } from "@/lib/sportDay";
import { pageMetadata } from "@/lib/seo";
import { SPORT_COPY } from "@/lib/sportContent";

// One cached page per day, like the main page. Visitors still use /tennis?date=YYYY-MM-DD:
// next.config.ts rewrites that address here.
export const revalidate = 600;

const copy = SPORT_COPY.tennis;

// The same page as /tennis for a different day, so it names /tennis as its address.
export const metadata = {
  ...pageMetadata({
    title: copy.metaTitle,
    description: copy.metaDescription,
    path: copy.path,
  }),
  keywords: copy.keywords,
};

export default async function TennisDayPage({
  params,
}: {
  params: Promise<{ date: string }>;
}) {
  const day = validSportDay((await params).date);
  if (!day) redirect(copy.path);
  return <SportRoute sport="tennis" date={day} />;
}
