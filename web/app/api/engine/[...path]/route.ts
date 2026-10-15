/**
 * A narrow pass-through from the browser to the engine, as the signed-in member.
 *
 * Only these prefixes are reachable: the administrator's API (the engine refuses anyone who is
 * not an administrator, whatever this route does), the premium plans, checkout and cancellation,
 * and the public content. Anything else gets a 404, so a new engine endpoint is never exposed to
 * browsers by accident.
 *
 * Almost everything is JSON. The one exception is the administrator's image upload
 * (`admin/media`): its body is the file itself (or a multipart form from the editor's image
 * dialog), so it is forwarded as bytes with its own content type, and the editor's dialog gets
 * the small HTML reply it expects.
 */

import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { ENGINE_URL, SESSION_COOKIE } from "@/lib/session";

const ALLOWED = [
  /^admin\//,
  /^premium\/plans$/,
  /^premium\/checkout$/,
  /^premium\/cancel$/,
  /^content\/(posts|picks|categories)/,
];

const UPLOAD = /^admin\/media$/;

function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  try {
    const host =
      request.headers.get("x-forwarded-host") ?? request.headers.get("host");
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

async function handle(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const joined = path.join("/");
  if (!ALLOWED.some((rule) => rule.test(joined)) || joined.includes("..")) {
    return NextResponse.json(
      { detail: { code: "not_found" } },
      { status: 404 },
    );
  }
  const method = request.method.toUpperCase();
  if (method !== "GET" && !sameOrigin(request)) {
    return NextResponse.json(
      { detail: { code: "bad_origin" } },
      { status: 403 },
    );
  }
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  const search = new URL(request.url).search;
  const hasBody = !["GET", "HEAD", "DELETE"].includes(method);
  const isUpload = UPLOAD.test(joined) && method === "POST";
  let upstream: Response;
  try {
    upstream = await fetch(`${ENGINE_URL}/${joined}${search}`, {
      method,
      headers: {
        accept: isUpload ? "application/json, text/html" : "application/json",
        ...(isUpload
          ? {
              "content-type":
                request.headers.get("content-type") ??
                "application/octet-stream",
            }
          : hasBody
            ? { "content-type": "application/json" }
            : {}),
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
      body: isUpload
        ? await request.arrayBuffer()
        : hasBody
          ? await request.text()
          : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(isUpload ? 60_000 : 20_000),
    });
  } catch {
    return NextResponse.json(
      {
        detail: {
          code: "unavailable",
          message: "The service is not reachable.",
        },
      },
      { status: 503 },
    );
  }
  if ((upstream.headers.get("content-type") ?? "").startsWith("text/html")) {
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "x-content-type-options": "nosniff",
      },
    });
  }
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

export { handle as GET, handle as POST, handle as PUT, handle as DELETE };
