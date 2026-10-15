"use client";

/**
 * The blog's list of articles. Writing and editing is in ArticleEditor.
 */

import Link from "next/link";
import { useState } from "react";
import { Message } from "@/components/auth/ui";
import { useAdminData } from "@/components/admin/useAdminData";
import { api } from "@/lib/clientApi";
import type { Post } from "@/lib/content";

function when(iso: string | null): string {
  if (!iso) return "";
  const withZone = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  return new Date(withZone).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function PostsAdmin() {
  const { data, error, loading, reload } = useAdminData<{ posts: Post[] }>(
    "admin/posts",
  );
  const [message, setMessage] = useState<string | null>(null);

  async function act(label: string, path: string, method = "POST") {
    setMessage(null);
    const result = await api(`/api/engine/${path}`, {
      method,
      body: method === "DELETE" ? undefined : {},
    });
    setMessage(result.ok ? label : (result.error?.message ?? "That did not work."));
    if (result.ok) await reload();
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[28px] font-black tracking-[-0.02em]">Blog</h1>
          <p className="mt-1 text-[14.5px] text-[var(--color-text-dim)]">
            Write, publish and remove articles.
          </p>
        </div>
        <Link href="/admin/posts/new" className="nt-cta nt-cta--primary">
          New article
        </Link>
      </header>

      {message && <Message tone="info">{message}</Message>}
      {loading && <p className="text-[14px] text-[var(--color-text-dim)]">Loading…</p>}
      {error && <Message tone="error">{error}</Message>}
      {data && data.posts.length === 0 && (
        <p className="rounded-[14px] border border-dashed border-[var(--color-line-strong)] p-6 text-[14.5px] text-[var(--color-text-dim)]">
          No articles yet. Write the first one.
        </p>
      )}

      <ul className="space-y-3">
        {data?.posts.map((post) => (
          <li
            key={post.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-[12px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-4"
          >
            <div className="min-w-0">
              <p className="truncate text-[16px] font-bold">{post.title}</p>
              <p className="mt-0.5 text-[12.5px] text-[var(--color-text-dim)]">
                <b
                  className={
                    post.status === "published"
                      ? "text-[var(--color-won)]"
                      : "text-[var(--color-text-dim)]"
                  }
                >
                  {post.status === "published" ? "Published" : "Draft"}
                </b>
                {post.category && ` · ${post.category}`}
                {post.premium_only && " · Premium"}
                {" · "}
                {post.status === "published"
                  ? when(post.published_at)
                  : `edited ${when(post.updated_at ?? post.created_at)}`}
                {post.status === "published" && (
                  <>
                    {" · "}
                    <Link
                      href={`/blog/${post.slug}`}
                      className="underline underline-offset-4"
                    >
                      view
                    </Link>
                  </>
                )}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link
                href={`/admin/posts/${post.id}`}
                className="nt-cta nt-cta--ghost !px-3 !py-1.5 text-[12px]"
              >
                Edit
              </Link>
              {post.status === "published" && (
                <button
                  type="button"
                  className="nt-cta nt-cta--ghost !px-3 !py-1.5 text-[12px]"
                  onClick={() =>
                    act("Unpublished.", `admin/posts/${post.id}/unpublish`)
                  }
                >
                  Unpublish
                </button>
              )}
              <button
                type="button"
                className="nt-cta !px-3 !py-1.5 text-[12px] border-[var(--color-lost)] text-[var(--color-lost)] hover:bg-[var(--color-lost)]/10"
                onClick={() => {
                  if (window.confirm(`Delete "${post.title}"? This cannot be undone.`)) {
                    void act("Deleted.", `admin/posts/${post.id}`, "DELETE");
                  }
                }}
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
