import { PageSkeleton } from "@/components/PageSkeleton";

// Shown the moment a link is clicked, for any page that has no loading screen of its own.
export default function Loading() {
  return <PageSkeleton />;
}
