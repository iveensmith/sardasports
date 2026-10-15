/**
 * Account actions: sign up, sign in, sign out, confirm an address, reset or change a password,
 * delete the account, read who is signed in.
 *
 * The browser talks to this route and this route talks to the engine, so the engine's address
 * and the session token stay on the server. This is also the only place the session cookie is
 * set or cleared.
 *
 * CSRF: every state-changing request must come from this site (its `Origin` host has to match
 * the host it was sent to), and the cookie is SameSite=Lax, so another site cannot make a
 * signed-in browser act.
 */

import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { ENGINE_URL, SESSION_COOKIE } from "@/lib/session";

interface ActionSpec {
  path: string;
  method?: "POST" | "GET" | "PATCH";
  /** Needs the member's session token. */
  auth?: boolean;
  /** Stores the session token returned in the response as the cookie. */
  startsSession?: boolean;
  /** Clears the cookie on success. */
  endsSession?: boolean;
}

const ACTIONS: Record<string, ActionSpec> = {
  register: { path: "/auth/register" },
  login: { path: "/auth/login", startsSession: true },
  logout: { path: "/auth/logout", auth: true, endsSession: true },
  "logout-all": { path: "/auth/logout-all", auth: true, endsSession: true },
  me: { path: "/auth/me", method: "GET", auth: true },
  "verify-email": { path: "/auth/verify-email" },
  "resend-verification": { path: "/auth/resend-verification" },
  "forgot-password": { path: "/auth/forgot-password" },
  "reset-password": { path: "/auth/reset-password" },
  "change-password": { path: "/auth/change-password", auth: true },
  "delete-account": {
    path: "/auth/delete-account",
    auth: true,
    endsSession: true,
  },
  profile: { path: "/auth/profile", method: "PATCH", auth: true },
};

function clientIp(request: Request): string {
  return (
    request.headers.get("cf-connecting-ip") ||
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    request.headers.get("x-real-ip") ||
    "unknown"
  );
}

function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true; // not a browser form post; a browser always sends Origin on POST
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
  { params }: { params: Promise<{ action: string }> },
) {
  const { action } = await params;
  const spec = ACTIONS[action];
  const method = request.method.toUpperCase();
  if (!spec || method !== (spec.method ?? "POST")) {
    return NextResponse.json(
      { detail: { code: "not_found" } },
      { status: 404 },
    );
  }
  if (method !== "GET" && !sameOrigin(request)) {
    return NextResponse.json(
      { detail: { code: "bad_origin", message: "Request refused." } },
      { status: 403 },
    );
  }

  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value ?? null;
  if (spec.auth && !token) {
    if (action === "logout" || action === "logout-all") {
      return NextResponse.json({ ok: true });
    }
    return NextResponse.json(
      {
        detail: {
          code: "not_signed_in",
          message: "Please sign in to continue.",
        },
      },
      { status: 401 },
    );
  }

  let body: unknown = undefined;
  if (method !== "GET") {
    body = await request.json().catch(() => ({}));
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${ENGINE_URL}${spec.path}`, {
      method,
      headers: {
        accept: "application/json",
        ...(body !== undefined ? { "content-type": "application/json" } : {}),
        ...(spec.auth && token ? { authorization: `Bearer ${token}` } : {}),
        "x-client-ip": clientIp(request),
        "user-agent": request.headers.get("user-agent") ?? "",
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    return NextResponse.json(
      {
        detail: {
          code: "unavailable",
          message:
            "The service is not reachable right now. Please try again shortly.",
        },
      },
      { status: 503 },
    );
  }

  const data = (await upstream.json().catch(() => ({}))) as Record<
    string,
    unknown
  >;

  if (spec.startsSession && upstream.ok && typeof data.token === "string") {
    const sessionValue = data.token;
    delete data.token; // the browser never sees the value in a response body
    const response = NextResponse.json(data, { status: 200 });
    response.cookies.set(SESSION_COOKIE, sessionValue, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 24 * 30,
    });
    return response;
  }

  const response = NextResponse.json(data, { status: upstream.status });
  if (spec.endsSession && upstream.ok) {
    response.cookies.delete(SESSION_COOKIE);
  }
  return response;
}

export { handle as GET, handle as POST, handle as PATCH };
