import { engineDownload } from "@/lib/api";

export const dynamic = "force-dynamic";

export function GET() {
  return engineDownload("/progress/matches.csv");
}
