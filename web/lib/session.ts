/**
 * The signed-in member, as the website's server sees them.
 *
 * The browser holds one cookie, `sd_session`: an opaque random value, HttpOnly (page scripts
 * cannot read it), SameSite=Lax and Secure in production. Everything about who the member is
 * and what they may see is decided by the engine from that value on every request; nothing about
 * a member is trusted from the browser.
 *
 * Reading the cookie makes a page render per request, so only the pages that must differ per
 * member do it (a premium post, the account page, the admin area). The header never does: it asks
 * `/api/auth/me` from the browser, so every other page stays cached and shared.
 */

import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";

export const SESSION_COOKIE = "sd_session";
export const ENGINE_URL = process.env.ENGINE_URL ?? "http://127.0.0.1:8000";

export interface Member {
  id: number;
  email: string;
  display_name: string | null;
  role: "member" | "admin";
  email_verified: boolean;
  over_18_confirmed: boolean;
  marketing_opt_in: boolean;
  created_at: string | null;
}

export interface Entitlement {
  premium: boolean;
  until: string | null;
  provider: string | null;
  cancel_at_period_end: boolean;
}

export interface Session {
  user: Member;
  entitlement: Entitlement;
}

export async function sessionToken(): Promise<string | null> {
  const jar = await cookies();
  return jar.get(SESSION_COOKIE)?.value ?? null;
}

/** An uncached call to the engine, optionally as a member. Never throws: status 503 on failure. */
export async function engineCall<T>(
  path: string,
  options: {
    method?: string;
    token?: string | null;
    body?: unknown;
    timeoutMs?: number;
  } = {},
): Promise<{ status: number; data: T | null }> {
  const headers: Record<string, string> = { accept: "application/json" };
  if (options.token) headers.authorization = `Bearer ${options.token}`;
  if (options.body !== undefined) headers["content-type"] = "application/json";
  try {
    const response = await fetch(`${ENGINE_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body:
        options.body !== undefined ? JSON.stringify(options.body) : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(options.timeoutMs ?? 10_000),
    });
    const data = (await response.json().catch(() => null)) as T | null;
    return { status: response.status, data };
  } catch {
    return { status: 503, data: null };
  }
}

/** The member for this request, or null (signed out, expired, or the engine unreachable). */
export async function getSession(): Promise<Session | null> {
  const token = await sessionToken();
  if (!token) return null;
  const { status, data } = await engineCall<Session>("/auth/me", { token });
  if (status !== 200 || !data) return null;
  return data;
}

/**
 * For the administrator's pages: the session, or a redirect to sign in, or a 404.
 *
 * A signed-in member who is not an administrator gets "not found", not "forbidden", so the
 * existence of the area is not confirmed to them. The engine enforces the same rule on every
 * admin call; this only decides what the page does.
 */
export async function requireAdmin(next: string): Promise<Session> {
  const session = await getSession();
  if (!session) redirect(`/login?next=${encodeURIComponent(next)}`);
  if (session.user.role !== "admin") notFound();
  return session;
}

