"use client";

/**
 * The blog: the list of posts, and the editor with a live preview.
 *
 * The preview uses the same renderer the public page uses, so what is shown here is what a reader
 * will see, and neither can render raw HTML.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Check, Field, Message, inputClass } from "@/components/auth/ui";
import { useAdminData } from "@/components/admin/useAdminData";
import { api } from "@/lib/clientApi";
import type { Post } from "@/lib/content";
import { renderMarkdown } from "@/lib/markdown";

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
            Write, publish and remove posts.
          </p>
        </div>
        <Link href="/admin/posts/new" className="nt-cta nt-cta--primary">
          New post
        </Link>
      </header>

      {message && <Message tone="info">{message}</Message>}
      {loading && <p className="text-[14px] text-[var(--color-text-dim)]">Loading…</p>}
      {error && <Message tone="error">{error}</Message>}
      {data && data.posts.length === 0 && (
        <p className="rounded-[14px] border border-dashed border-[var(--color-line-strong)] p-6 text-[14.5px] text-[var(--color-text-dim)]">
          No posts yet. Write the first one.
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

export function PostEditor({ postId }: { postId: number | null }) {
  const router = useRouter();
  const [loaded, setLoaded] = useState(postId === null);
  const [title, setTitle] = useState("");
  const [excerpt, setExcerpt] = useState("");
  const [body, setBody] = useState("");
  const [premium, setPremium] = useState(false);
  const [status, setStatus] = useState<"draft" | "published">("draft");
  const [slug, setSlug] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "error" | "success"; text: string } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (postId === null) return;
    let alive = true;
    api<{ post: Post }>(`/api/engine/admin/posts/${postId}`).then((result) => {
      if (!alive) return;
      if (result.ok && result.data) {
        const p = result.data.post;
        setTitle(p.title);
        setExcerpt(p.excerpt);
        setBody(p.body);
        setPremium(p.premium_only);
        setStatus(p.status);
        setSlug(p.slug);
        setLoaded(true);
      } else {
        setMessage({ tone: "error", text: "Could not load this post." });
      }
    });
    return () => {
      alive = false;
    };
  }, [postId]);

  async function save(publish: boolean) {
    setBusy(true);
    setMessage(null);
    const payload = { title, excerpt, body, premium_only: premium, publish };
    const result =
      postId === null
        ? await api<{ post: Post }>("/api/engine/admin/posts", { body: payload })
        : await api<{ post: Post }>(`/api/engine/admin/posts/${postId}`, {
            method: "PUT",
            body: payload,
          });
    setBusy(false);
    if (result.ok && result.data) {
      const saved = result.data.post;
      setStatus(saved.status);
      setSlug(saved.slug);
      setMessage({
        tone: "success",
        text: publish ? "Published." : "Saved.",
      });
      if (postId === null) router.replace(`/admin/posts/${saved.id}`);
    } else {
      setMessage({
        tone: "error",
        text: result.error?.message ?? "Could not save the post.",
      });
    }
  }

  if (!loaded && !message) {
    return <p className="text-[14px] text-[var(--color-text-dim)]">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-[28px] font-black tracking-[-0.02em]">
          {postId === null ? "New post" : "Edit post"}
        </h1>
        <Link
          href="/admin/posts"
          className="text-[13.5px] font-semibold text-[var(--color-gold-bright)] underline underline-offset-4"
        >
          All posts
        </Link>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <Field
            id="title"
            label="Title"
            value={title}
            maxLength={160}
            onChange={(e) => setTitle(e.target.value)}
          />
          <div>
            <label htmlFor="excerpt" className="text-[13px] font-semibold">
              Summary (shown to everyone, including on premium posts: keep the analysis out of it)
            </label>
            <textarea
              id="excerpt"
              rows={2}
              maxLength={400}
              value={excerpt}
              onChange={(e) => setExcerpt(e.target.value)}
              className={`${inputClass} mt-1.5`}
            />
          </div>
          <div>
            <label htmlFor="body" className="text-[13px] font-semibold">
              Post (Markdown: # heading, **bold**, *italic*, - list, [link](https://…))
            </label>
            <textarea
              id="body"
              rows={18}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className={`${inputClass} mt-1.5 font-mono text-[14px]`}
            />
          </div>
          <Check
            id="premium"
            checked={premium}
            onChange={(e) => setPremium(e.target.checked)}
          >
            Premium only: non-members see the summary and a prompt to join.
          </Check>
          {message && <Message tone={message.tone}>{message.text}</Message>}
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              disabled={busy}
              onClick={() => save(true)}
              className="nt-cta nt-cta--primary disabled:opacity-60"
            >
              {status === "published" ? "Update post" : "Publish"}
            </button>
            {status !== "published" && (
              <button
                type="button"
                disabled={busy}
                onClick={() => save(false)}
                className="nt-cta nt-cta--ghost disabled:opacity-60"
              >
                Save draft
              </button>
            )}
            {status === "published" && slug && (
              <Link
                href={`/blog/${slug}`}
                className="nt-cta nt-cta--ghost"
              >
                View post
              </Link>
            )}
          </div>
        </div>

        <div>
          <p className="text-[13px] font-semibold">Preview</p>
          <article className="mt-1.5 min-h-[300px] space-y-4 rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-5 text-[15.5px]">
            <h2 className="text-[26px] leading-tight font-black tracking-[-0.02em]">
              {title || "Untitled"}
            </h2>
            {renderMarkdown(body)}
          </article>
        </div>
      </div>
    </div>
  );
}
