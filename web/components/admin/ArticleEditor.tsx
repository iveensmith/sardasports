"use client";

/**
 * Create and edit a blog article: title, category, tags, featured image, the rich-text body and
 * one Publish button. The layout follows the owner's reference; the styling is in
 * article-editor.css.
 *
 * Besides what the reference shows there is a summary box and a "premium only" switch, because a
 * premium post must not give itself away in its summary (see content_service.save_post), and a
 * "Save draft" button, so an article can be kept unpublished.
 */

import "./article-editor.css";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { RichTextEditor } from "@/components/admin/RichTextEditor";
import { api } from "@/lib/clientApi";
import type { Post } from "@/lib/content";

const MAX_TAGS = 8;
const MAX_TAG_LENGTH = 30;
const MAX_IMAGE_BYTES = 6 * 1024 * 1024;
const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** An older, plain-text post as paragraphs the editor can open (its text is kept as written). */
function plainToHtml(text: string): string {
  return text
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) => `<p>${escapeHtml(block).replace(/\n/g, "<br>")}</p>`)
    .join("\n");
}

type Notice = { tone: "ok" | "error" | "info"; text: string } | null;

export function ArticleEditor({ postId }: { postId: number | null }) {
  const router = useRouter();
  const [loaded, setLoaded] = useState(postId === null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [tagDraft, setTagDraft] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const [imageBusy, setImageBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [excerpt, setExcerpt] = useState("");
  const [premium, setPremium] = useState(false);
  const [status, setStatus] = useState<"draft" | "published">("draft");
  const [slug, setSlug] = useState<string | null>(null);
  const [initialHtml, setInitialHtml] = useState("");
  const [legacy, setLegacy] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const [notice, setNotice] = useState<Notice>(null);
  const [busy, setBusy] = useState(false);

  const getHtml = useRef<() => string>(() => "");
  const fileInput = useRef<HTMLInputElement>(null);
  const registerEditor = useCallback((getter: () => string) => {
    getHtml.current = getter;
  }, []);

  useEffect(() => {
    let alive = true;
    api<{ categories: string[] }>("/api/engine/content/categories").then((r) => {
      if (alive && r.ok && r.data) setCategories(r.data.categories);
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (postId === null) return;
    let alive = true;
    api<{ post: Post }>(`/api/engine/admin/posts/${postId}`).then((result) => {
      if (!alive) return;
      if (result.ok && result.data) {
        const p = result.data.post;
        setTitle(p.title);
        setCategory(p.category ?? "");
        setTags(p.tags ?? []);
        setImage(p.featured_image ?? null);
        setExcerpt(p.excerpt);
        setPremium(p.premium_only);
        setStatus(p.status);
        setSlug(p.slug);
        if (p.body_format === "markdown") {
          setLegacy(true);
          setInitialHtml(plainToHtml(p.body));
        } else {
          setInitialHtml(p.body);
        }
        setLoaded(true);
      } else {
        setLoadError("Could not load this article.");
      }
    });
    return () => {
      alive = false;
    };
  }, [postId]);

  // --- tags -------------------------------------------------------------------------------

  function addTags(raw: string) {
    const incoming = raw
      .split(",")
      .map((t) => t.replace(/[<>]/g, "").replace(/\s+/g, " ").trim())
      .filter(Boolean)
      .map((t) => t.slice(0, MAX_TAG_LENGTH));
    if (incoming.length === 0) return;
    setTags((current) => {
      const next = [...current];
      for (const tag of incoming) {
        if (next.length >= MAX_TAGS) break;
        if (!next.some((t) => t.toLowerCase() === tag.toLowerCase())) next.push(tag);
      }
      return next;
    });
  }

  function onTagChange(value: string) {
    if (value.includes(",")) {
      const last = value.lastIndexOf(",");
      addTags(value.slice(0, last));
      setTagDraft(value.slice(last + 1));
    } else {
      setTagDraft(value);
    }
  }

  // --- featured image ---------------------------------------------------------------------

  async function upload(file: File) {
    if (!IMAGE_TYPES.includes(file.type)) {
      setNotice({ tone: "error", text: "Use a JPEG, PNG or WebP image." });
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setNotice({ tone: "error", text: "Images can be up to 6 MB." });
      return;
    }
    setImageBusy(true);
    setNotice(null);
    try {
      const response = await fetch("/api/engine/admin/media", {
        method: "POST",
        headers: { "content-type": file.type },
        body: file,
        credentials: "same-origin",
      });
      const data = (await response.json().catch(() => null)) as {
        url?: string;
        error?: { message?: string };
      } | null;
      if (response.ok && data?.url) {
        setImage(data.url);
      } else {
        setNotice({
          tone: "error",
          text: data?.error?.message ?? "The image could not be uploaded.",
        });
      }
    } catch {
      setNotice({ tone: "error", text: "The image could not be uploaded." });
    } finally {
      setImageBusy(false);
    }
  }

  // --- saving -----------------------------------------------------------------------------

  async function save(publish: boolean) {
    const html = getHtml.current();
    if (!title.trim()) {
      setNotice({ tone: "error", text: "Give the article a title." });
      return;
    }
    if (!html.trim()) {
      setNotice({ tone: "error", text: "The article has no content yet." });
      return;
    }
    // A tag typed but not yet confirmed with a comma still counts.
    const pending = tagDraft
      .replace(/[<>,]/g, "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, MAX_TAG_LENGTH);
    const allTags =
      pending &&
      tags.length < MAX_TAGS &&
      !tags.some((t) => t.toLowerCase() === pending.toLowerCase())
        ? [...tags, pending]
        : tags;
    setBusy(true);
    setNotice(null);
    const payload = {
      title,
      excerpt,
      body: html,
      premium_only: premium,
      publish,
      category: category || null,
      tags: allTags,
      featured_image: image,
    };
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
      setTags(saved.tags);
      setTagDraft("");
      setNotice({
        tone: "ok",
        text: publish
          ? status === "published"
            ? "Article updated."
            : "Article published."
          : "Draft saved.",
      });
      if (postId === null) router.replace(`/admin/posts/${saved.id}`);
    } else {
      setNotice({
        tone: "error",
        text: result.error?.message ?? "Could not save the article.",
      });
    }
  }

  const heading = postId === null ? "Create New Article" : "Edit Article";

  return (
    <div className="ae-page">
      <Link href="/admin/posts" className="ae-back">
        All articles
      </Link>
      <h1 className="ae-heading">{heading}</h1>
      <p className="ae-sub">Write and publish professional articles.</p>

      {loadError && (
        <p className="ae-notice ae-notice--error" role="alert">
          {loadError}
        </p>
      )}

      {!loaded && !loadError && (
        <p className="ae-sub" style={{ marginTop: 26 }}>
          Loading…
        </p>
      )}

      {loaded && (
        <div className="ae-card">
          <div className="ae-body">
            <div className="ae-field">
              <label className="ae-label" htmlFor="ae-title">
                Article Title
              </label>
              <input
                id="ae-title"
                className="ae-input"
                type="text"
                maxLength={160}
                placeholder="Enter article title..."
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div className="ae-field">
              <label className="ae-label" htmlFor="ae-category">
                Category
              </label>
              <select
                id="ae-category"
                className="ae-select"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                <option value="">---------</option>
                {categories.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>

            <div className="ae-field">
              <label className="ae-label" htmlFor="ae-tags">
                Tags
              </label>
              <div className="ae-tags">
                {tags.map((tag) => (
                  <span key={tag} className="ae-chip">
                    {tag}
                    <button
                      type="button"
                      aria-label={`Remove tag ${tag}`}
                      onClick={() =>
                        setTags((current) => current.filter((t) => t !== tag))
                      }
                    >
                      ×
                    </button>
                  </span>
                ))}
                <input
                  id="ae-tags"
                  type="text"
                  value={tagDraft}
                  placeholder={tags.length === 0 ? "Type tag and press comma" : ""}
                  disabled={tags.length >= MAX_TAGS}
                  onChange={(e) => onTagChange(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addTags(tagDraft);
                      setTagDraft("");
                    } else if (
                      e.key === "Backspace" &&
                      tagDraft === "" &&
                      tags.length > 0
                    ) {
                      setTags((current) => current.slice(0, -1));
                    }
                  }}
                  onBlur={() => {
                    addTags(tagDraft);
                    setTagDraft("");
                  }}
                />
              </div>
              <p className="ae-help">Type a tag and press comma to add it.</p>
            </div>

            <div className="ae-field">
              <span className="ae-label" id="ae-image-label">
                Featured Image
              </span>
              <div
                role="button"
                tabIndex={0}
                aria-labelledby="ae-image-label"
                className="ae-drop"
                data-over={dragOver}
                onClick={() => fileInput.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    fileInput.current?.click();
                  }
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  const file = e.dataTransfer.files?.[0];
                  if (file) void upload(file);
                }}
              >
                <span className="ae-plus" aria-hidden>
                  {imageBusy ? "…" : "+"}
                </span>
                <span className="ae-drop-note">
                  {imageBusy ? "Uploading…" : "JPEG, PNG or WebP, up to 6 MB"}
                </span>
              </div>
              <input
                ref={fileInput}
                type="file"
                accept={IMAGE_TYPES.join(",")}
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void upload(file);
                  e.target.value = "";
                }}
              />
              <div className="ae-preview">
                {image ? (
                  <>
                    {/* A plain img: the file is served by this site and sized by the engine. */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={image} alt="Featured image preview" />
                    <button
                      type="button"
                      className="ae-remove"
                      onClick={() => setImage(null)}
                    >
                      Remove
                    </button>
                  </>
                ) : (
                  <span>No image selected</span>
                )}
              </div>
            </div>

            <div className="ae-field">
              <span className="ae-label">Article Content</span>
              {legacy && (
                <p className="ae-notice ae-notice--info" style={{ marginTop: 0, marginBottom: 12 }}>
                  This article was written in the older plain-text format. It has been
                  opened as paragraphs; headings and bold text from that format are not
                  carried over. Saving stores it in the new format.
                </p>
              )}
              <RichTextEditor initialHtml={initialHtml} register={registerEditor} />
            </div>

            <div className="ae-field">
              <label className="ae-label" htmlFor="ae-excerpt">
                Summary (optional)
              </label>
              <textarea
                id="ae-excerpt"
                className="ae-textarea"
                maxLength={400}
                rows={2}
                placeholder="Shown on the blog list and in search results. Left empty, it is taken from the start of the article."
                value={excerpt}
                onChange={(e) => setExcerpt(e.target.value)}
              />
              <p className="ae-help">
                The summary is shown to everyone, including on premium articles, so keep
                the analysis out of it.
              </p>
            </div>

            <div className="ae-field">
              <label className="ae-check" htmlFor="ae-premium">
                <input
                  id="ae-premium"
                  type="checkbox"
                  checked={premium}
                  onChange={(e) => setPremium(e.target.checked)}
                />
                <span>
                  Premium only: members read the article; everyone else sees the summary
                  and a prompt to join.
                </span>
              </label>
            </div>

            {notice && (
              <p
                className={`ae-notice ae-notice--${notice.tone}`}
                role={notice.tone === "error" ? "alert" : "status"}
              >
                {notice.text}
              </p>
            )}
          </div>

          <div className="ae-footer">
            {status === "published" && slug && (
              <Link href={`/blog/${slug}`} className="ae-spacer">
                View article
              </Link>
            )}
            {status !== "published" && (
              <button
                type="button"
                className="ae-button ae-button--ghost"
                disabled={busy || imageBusy}
                onClick={() => save(false)}
              >
                Save draft
              </button>
            )}
            <button
              type="button"
              className="ae-button ae-button--primary"
              disabled={busy || imageBusy}
              onClick={() => save(true)}
            >
              {busy
                ? "Saving…"
                : status === "published"
                  ? "Update Article"
                  : "Publish Article"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
