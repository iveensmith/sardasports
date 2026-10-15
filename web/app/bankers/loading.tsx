import { PageSkeleton } from "@/components/PageSkeleton";

// A table of fixtures is coming: the same shape, so the page does not jump when it arrives.
export default function Loading() {
  return <PageSkeleton variant="board" />;
}
