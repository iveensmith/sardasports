import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { renderMarkdown } from "@/lib/markdown";
import type { Post } from "@/lib/content";
import { engineCall, sessionToken } from "@/lib/session";
import { absoluteUrl } from "@/lib/site";

// Per request: whether the body is shown depends on who is asking (a premium post).
export const dynamic = "force-dynamic";

async function load(slug: string): Promise<Post | null> {
  const token = await sessionToken();
  const { status, data } = await engineCall<{ post: Post }>(
    `/content/posts/${encodeURIComponent(slug)}`,
    { token },
  );
  if (status !== 200 || !data) return null;
  return data.post;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const { data } = await engineCall<{ post: Post }>(
    `/content/posts/${encodeURIComponent(slug)}`,
  );
  const post = data?.post;
  if (!post) return { title: "Post not found" };
  return {
    title: post.title,
    description: post.excerpt.slice(0, 155),
    alternates: { canonical: `/blog/${post.slug}` },
    openGraph: {
      title: post.title,
      description: post.excerpt.slice(0, 155),
      url: absoluteUrl(`/blog/${post.slug}`),
      type: "article",
      ...(post.featured_image
        ? { images: [{ url: absoluteUrl(post.featured_image) }] }
        : {}),
    },
  };
}

function day(iso: string | null): string {
  if (!iso) return "";
  const withZone = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  return new Date(withZone).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

export default async function PostPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const post = await load(slug);
  if (!post) notFound();

  return (
    <article className="mx-auto w-full max-w-[720px] px-4 py-12 sm:px-6 sm:py-16">
      <Link
        href="/blog"
        className="text-[13px] font-semibold text-[var(--color-gold-bright)] underline-offset-4 hover:underline"
      >
        All posts
      </Link>
      <header className="mt-4">
        <p className="flex flex-wrap items-center gap-2 text-[12.5px] text-[var(--color-text-faint)]">
          {day(post.published_at)}
          {post.category && (
            <Link
              href={`/blog?category=${encodeURIComponent(post.category)}`}
              className="font-semibold text-[var(--color-text-dim)] underline-offset-4 hover:underline"
            >
              {post.category}
            </Link>
          )}
          {post.premium_only && (
            <span className="rounded bg-[var(--color-gold)] px-1.5 py-0.5 text-[10px] font-extrabold tracking-wider text-[var(--color-ink-on-accent)] uppercase">
              Premium
            </span>
          )}
        </p>
        <h1 className="mt-2 text-[clamp(1.9rem,4.5vw,2.6rem)] leading-[1.1] font-black tracking-[-0.025em]">
          {post.title}
        </h1>
        {post.featured_image && (
          // A plain img: served by this site, already resized by the engine.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={post.featured_image}
            alt=""
            className="mt-6 h-auto w-full rounded-[14px] border border-[var(--color-line)]"
          />
        )}
      </header>

      {post.locked ? (
        <div className="mt-8 space-y-5">
          <p className="text-[16px] leading-relaxed text-[var(--color-text-dim)]">
            {post.excerpt}
          </p>
          <div className="rounded-[14px] border-2 border-[var(--color-gold)]/70 bg-[var(--color-surface)] p-6">
            <p className="text-[17px] font-bold">This post is for premium members</p>
            <p className="mt-1.5 text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
              Premium sells early access: every engine prediction before
              kick-off, and the write-ups. The record stays open to everyone.
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Link href="/premium" className="nt-cta nt-cta--primary">
                See premium
              </Link>
              <Link
                href={`/login?next=/blog/${post.slug}`}
                className="nt-cta nt-cta--ghost"
              >
                Log in
              </Link>
            </div>
          </div>
        </div>
      ) : (
        post.body_format === "markdown" ? (
          <div className="mt-8 space-y-4 text-[16.5px] text-[var(--color-text)]">
            {renderMarkdown(post.body)}
          </div>
        ) : (
          // The engine rebuilt this HTML from an allow-list when the article was saved
          // (app/services/html_sanitize.py), so it is shown as stored.
          <div
            className="post-body mt-8 text-[var(--color-text)]"
            dangerouslySetInnerHTML={{ __html: post.body }}
          />
        )
      )}

      {post.tags.length > 0 && !post.locked && (
        <ul className="mt-10 flex flex-wrap gap-2" aria-label="Tags">
          {post.tags.map((tag) => (
            <li
              key={tag}
              className="rounded-full border border-[var(--color-line-strong)] px-3 py-1 text-[12.5px] text-[var(--color-text-dim)]"
            >
              {tag}
            </li>
          ))}
        </ul>
      )}

      <p className="mt-12 border-t border-[var(--color-line)] pt-5 text-[12.5px] leading-relaxed text-[var(--color-text-faint)]">
        18+ &middot; For information only, not betting advice. Predictions
        describe probability, not certainty.
      </p>
    </article>
  );
}
