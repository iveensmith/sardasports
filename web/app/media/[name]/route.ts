/**
 * Blog images, as visitors reach them: `/media/<name>`.
 *
 * The files live with the engine (on the data volume), not in this container, so this fetches the
 * one named file and passes it on. The name is checked against the exact shape an upload gets
 * before anything is requested, so this cannot be used to read any other path. Names are
 * random and never reused for different bytes, which is why the copy can be kept for a year.
 */

import { ENGINE_URL } from "@/lib/session";

const NAME = /^[a-f0-9]{32}\.(jpg|png|webp)$/;

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  if (!NAME.test(name)) return new Response("Not found", { status: 404 });
  let upstream: Response;
  try {
    upstream = await fetch(`${ENGINE_URL}/content/media/${name}`, {
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    return new Response("Unavailable", { status: 503 });
  }
  if (!upstream.ok || !upstream.body) {
    return new Response("Not found", { status: 404 });
  }
  return new Response(upstream.body, {
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "image/jpeg",
      "cache-control": "public, max-age=31536000, immutable",
      "x-content-type-options": "nosniff",
    },
  });
}
