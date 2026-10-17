"use client";

/**
 * A club's crest, with the monogram as its fallback.
 *
 * Crests come from the data provider's media server, so an image can fail:
 * the server is down, the id has no picture, the reader is offline. A broken
 * image icon beside a team name is worse than the initials it replaced, so on
 * any failure this swaps to the same disc `TeamCrest` draws for a club with no
 * crest. That needs a little script, which is why this one piece is a client
 * component and the rest of `TeamCrest` is not.
 *
 * The check on mount covers an image that already failed before React took
 * over the page (the `error` event is not replayed to handlers attached after
 * it fired).
 */

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

export function CrestImage({
  src,
  initials,
  name,
  size,
}: {
  src: string;
  initials: string | null;
  name: string;
  size: number;
}) {
  const [failed, setFailed] = useState(false);
  const ref = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const img = ref.current;
    if (img && img.complete && img.naturalWidth === 0) setFailed(true);
  }, []);

  if (failed) {
    return (
      <span
        aria-hidden
        title={name}
        className="inline-flex shrink-0 items-center justify-center rounded-full border border-[var(--color-line-strong)] bg-[var(--color-surface-raised)] font-semibold text-[var(--color-text-faint)]"
        style={{
          width: size,
          height: size,
          fontSize: size <= 20 ? 8.5 : size >= 40 ? 16 : 11,
        }}
      >
        {initials ?? "?"}
      </span>
    );
  }

  return (
    <span
      className="inline-flex shrink-0 items-center justify-center"
      style={{ width: size, height: size }}
    >
      {/* The picture is requested through Next's image optimiser, so the browser gets a copy
          resized to this box (see `images` in next.config.ts), not the provider's full-size file. */}
      <Image
        ref={ref}
        src={src}
        alt=""
        width={size}
        height={size}
        onError={() => setFailed(true)}
        className="h-full w-full object-contain"
      />
      <span className="sr-only">{name}</span>
    </span>
  );
}
