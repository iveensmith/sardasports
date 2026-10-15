import { SportRoute } from "@/components/sport/SportRoute";
import { pageMetadata } from "@/lib/seo";
import { SPORT_COPY } from "@/lib/sportContent";

// No query string is read here, so this is an ordinary cached page. A day's board is
// /tennis/d/YYYY-MM-DD, which next.config.ts serves for /tennis?date=YYYY-MM-DD.
export const revalidate = 600;

const copy = SPORT_COPY.tennis;

export const metadata = {
  ...pageMetadata({
    title: copy.metaTitle,
    description: copy.metaDescription,
    path: copy.path,
  }),
  keywords: copy.keywords,
};

export default function TennisPage() {
  return <SportRoute sport="tennis" />;
}
