import { SportRoute } from "@/components/sport/SportRoute";
import { pageMetadata } from "@/lib/seo";
import { SPORT_COPY } from "@/lib/sportContent";

export const revalidate = 600;

const copy = SPORT_COPY.basketball;

export const metadata = {
  ...pageMetadata({
    title: copy.metaTitle,
    description: copy.metaDescription,
    path: copy.path,
  }),
  keywords: copy.keywords,
};

/** A real YYYY-MM-DD, or null. Anything else in the URL is ignored, not echoed. */
function validDate(value: string | string[] | undefined): string | null {
  const first = Array.isArray(value) ? value[0] : value;
  return first && /^\d{4}-\d{2}-\d{2}$/.test(first) ? first : null;
}

export default async function BasketballPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const date = validDate((await searchParams).date);
  return <SportRoute sport="basketball" date={date} />;
}
