/**
 * A small, safe Markdown renderer for blog posts.
 *
 * Posts are written by an administrator, but they are still never trusted as HTML: nothing is
 * injected as markup. The text is parsed into React elements, so a `<script>` in a post is
 * shown as text, and a link can only be http, https, mailto or a path on this site.
 *
 * Supported: headings (#, ##, ###), paragraphs, bullet and numbered lists, block quotes,
 * horizontal rules, fenced code, **bold**, *italic*, `code` and [links](https://...).
 * That is all a post needs, and nothing outside this list can do anything.
 */

import type { ReactNode } from "react";

const SAFE_LINK = /^(https?:\/\/|mailto:|\/(?!\/))/i;

function inline(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = [];
  // Order matters: code first (its contents are literal), then links, bold, italic.
  const pattern =
    /(`[^`]+`)|(\[[^\]]+\]\([^)\s]+\))|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let n = 0;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${keyPrefix}-${n++}`;
    if (token.startsWith("`")) {
      out.push(
        <code
          key={key}
          className="rounded bg-[var(--color-surface-raised)] px-1.5 py-0.5 text-[0.92em]"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("[")) {
      const close = token.indexOf("](");
      const label = token.slice(1, close);
      const href = token.slice(close + 2, -1);
      if (SAFE_LINK.test(href)) {
        out.push(
          <a
            key={key}
            href={href}
            rel="noopener noreferrer nofollow"
            className="text-[var(--color-gold-bright)] underline underline-offset-4"
          >
            {label}
          </a>,
        );
      } else {
        out.push(label); // an unsafe address is shown as its label, as plain text
      }
    } else if (token.startsWith("**")) {
      out.push(
        <strong key={key} className="font-bold">
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      out.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
    last = match.index + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function renderMarkdown(source: string): ReactNode[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  const flushParagraph = (buffer: string[]) => {
    if (buffer.length === 0) return;
    const k = `p${key++}`;
    blocks.push(
      <p key={k} className="leading-relaxed">
        {inline(buffer.join(" "), k)}
      </p>,
    );
  };

  let paragraph: string[] = [];
  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      flushParagraph(paragraph);
      paragraph = [];
      i++;
      continue;
    }

    const fence = line.match(/^```/);
    if (fence) {
      flushParagraph(paragraph);
      paragraph = [];
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        code.push(lines[i]);
        i++;
      }
      i++; // the closing fence
      blocks.push(
        <pre
          key={`c${key++}`}
          className="overflow-x-auto rounded-[var(--radius-md)] bg-[var(--color-surface-raised)] p-4 text-[13px]"
        >
          <code>{code.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      flushParagraph(paragraph);
      paragraph = [];
      const level = heading[1].length;
      const k = `h${key++}`;
      const content = inline(heading[2], k);
      if (level === 1) {
        blocks.push(
          <h2 key={k} className="mt-6 text-[26px] font-bold tracking-[-0.02em]">
            {content}
          </h2>,
        );
      } else if (level === 2) {
        blocks.push(
          <h3 key={k} className="mt-5 text-[21px] font-bold tracking-[-0.015em]">
            {content}
          </h3>,
        );
      } else {
        blocks.push(
          <h4 key={k} className="mt-4 text-[17px] font-bold">
            {content}
          </h4>,
        );
      }
      i++;
      continue;
    }

    if (/^(-{3,}|\*{3,})\s*$/.test(line)) {
      flushParagraph(paragraph);
      paragraph = [];
      blocks.push(
        <hr key={`r${key++}`} className="border-[var(--color-line)]" />,
      );
      i++;
      continue;
    }

    const quote = line.match(/^>\s?(.*)$/);
    if (quote) {
      flushParagraph(paragraph);
      paragraph = [];
      const parts: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        parts.push(lines[i].replace(/^>\s?/, ""));
        i++;
      }
      const k = `q${key++}`;
      blocks.push(
        <blockquote
          key={k}
          className="border-l-[3px] border-[var(--color-gold)] pl-4 text-[var(--color-text-dim)]"
        >
          {inline(parts.join(" "), k)}
        </blockquote>,
      );
      continue;
    }

    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      flushParagraph(paragraph);
      paragraph = [];
      const ordered = Boolean(numbered);
      const items: string[] = [];
      const itemPattern = ordered ? /^\s*\d+[.)]\s+(.*)$/ : /^\s*[-*]\s+(.*)$/;
      while (i < lines.length) {
        const m = lines[i].match(itemPattern);
        if (!m) break;
        items.push(m[1]);
        i++;
      }
      const k = `l${key++}`;
      const children = items.map((item, index) => (
        <li key={`${k}-${index}`}>{inline(item, `${k}-${index}`)}</li>
      ));
      blocks.push(
        ordered ? (
          <ol key={k} className="list-decimal space-y-1.5 pl-6">
            {children}
          </ol>
        ) : (
          <ul key={k} className="list-disc space-y-1.5 pl-6">
            {children}
          </ul>
        ),
      );
      continue;
    }

    paragraph.push(line.trim());
    i++;
  }
  flushParagraph(paragraph);
  return blocks;
}
