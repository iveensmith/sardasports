import { notFound } from "next/navigation";
import { PostEditor } from "@/components/admin/PostsAdmin";

export default async function EditPostPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const postId = Number(id);
  if (!Number.isInteger(postId) || postId < 1) notFound();
  return <PostEditor postId={postId} />;
}
