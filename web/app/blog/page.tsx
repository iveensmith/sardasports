import Link from "next/link";
import type { Post } from "@/lib/content";
import { engineCall } from "@/lib/session";
import { pageMetadata } from "@/lib/seo";

export const revalidate = 120;

export const metadata = pageMetadata({
  title: "Blog: football, basketball and tennis analysis",
  description:
    "Match previews and analysis from the SARDASPORTS editor, written next to the numbers the engine produces.",
  path: "/blog",
});

function day(iso: string | null): string {
  if (!iso) return "";
  return new Date(`${iso}${/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? "" : "Z"}`).toLocaleDateString(
    "en-GB",
    { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" },
  );
}

export default async function BlogPage() {
  const { data } = await engineCall<{ total: number; posts: Post[] }>(
    "/content/posts?limit=50",
  );
  const posts = data?.posts ?? [];
  return (
    <div className="mx-auto w-full max-w-[860px] px-4 py-12 sm:px-6 sm:py-16">
      <header>
        <p className="text-[12px] font-extrabold tracking-[0.14em] text-[var(--color-gold-bright)] uppercase">
          The blog
        </p>
        <h1 className="mt-2 text-[clamp(1.9rem,4.5vw,2.7rem)] leading-tight font-black tracking-[-0.02em]">
          Analysis and previews
        </h1>
        <p className="mt-3 max-w-[60ch] text-[15px] leading-relaxed text-[var(--color-text-dim)]">
          Written by the editor, next to the numbers. The engine&rsquo;s own
          predictions stay on the{" "}
          <Link href="/matches" className="underline underline-offset-4">
            boards
          </Link>
          ; this is where the reasoning gets room.
        </p>
      </header>

      {posts.length === 0 ? (
        <p className="mt-10 rounded-[14px] border border-dashed border-[var(--color-line-strong)] p-6 text-[14.5px] text-[var(--color-text-dim)]">
          No posts yet. They will appear here as they are published.
        </p>
      ) : (
        <ul className="mt-10 space-y-4">
          {posts.map((post) => (
            <li key={post.id}>
              <Link
                href={`/blog/${post.slug}`}
                className="block rounded-[14px] border border-[var(--color-line-strong)] bg-[var(--color-surface)] p-5 transition-colors hover:border-[var(--color-gold)]/60"
              >
                <p className="flex flex-wrap items-center gap-2 text-[12px] text-[var(--color-text-faint)]">
                  <span>{day(post.published_at)}</span>
                  {post.premium_only && (
                    <span className="rounded bg-[var(--color-gold)] px-1.5 py-0.5 text-[10px] font-extrabold tracking-wider text-[var(--color-ink-on-accent)] uppercase">
                      Premium
                    </span>
                  )}
                </p>
                <h2 className="mt-1.5 text-[20px] leading-snug font-bold tracking-[-0.01em]">
                  {post.title}
                </h2>
                <p className="mt-2 text-[14.5px] leading-relaxed text-[var(--color-text-dim)]">
                  {post.excerpt}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
