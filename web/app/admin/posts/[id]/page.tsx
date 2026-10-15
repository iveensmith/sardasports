import { notFound } from "next/navigation";
import { ArticleEditor } from "@/components/admin/ArticleEditor";

export default async function EditPostPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const postId = Number(id);
  if (!Number.isInteger(postId) || postId < 1) notFound();
  return <ArticleEditor postId={postId} />;
}
