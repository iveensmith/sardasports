/**
 * The Contact form's endpoint.
 *
 * The browser talks to this route and this route talks to the engine, so the
 * engine's address stays server-side like every other call on the site.
 *
 * It also derives the opaque visitor token the engine uses to rate-limit. The
 * token is a one-way hash of the visitor's address and the date, so it changes
 * every day; the engine only counts with it, holds it in memory for an hour at
 * most, and never writes it to the database. That keeps the form's abuse
 * protection from turning into a log of who wrote in.
 */

import { createHash } from "node:crypto";
import { NextResponse } from "next/server";

const ENGINE_URL = process.env.ENGINE_URL ?? "http://127.0.0.1:8000";

function visitorToken(request: Request): string {
  const forwarded = request.headers
    .get("x-forwarded-for")
    ?.split(",")[0]
    ?.trim();
  const address = forwarded || request.headers.get("x-real-ip") || "unknown";
  const day = new Date().toISOString().slice(0, 10);
  return createHash("sha256")
    .update(`${day}|${address}`)
    .digest("hex")
    .slice(0, 32);
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      {
        errors: {
          message: "Something went wrong with that message. Please try again.",
        },
      },
      { status: 400 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${ENGINE_URL}/contact`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-contact-client": visitorToken(request),
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15_000),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      {
        error:
          "The message could not be sent right now. Please try again in a few minutes.",
      },
      { status: 503 },
    );
  }

  const payload = (await upstream.json().catch(() => ({}))) as {
    ok?: boolean;
    detail?: string | { errors?: Record<string, string> };
  };

  if (upstream.ok) return NextResponse.json({ ok: true });

  if (
    upstream.status === 422 &&
    payload.detail &&
    typeof payload.detail === "object" &&
    !Array.isArray(payload.detail) &&
    payload.detail.errors &&
    Object.keys(payload.detail.errors).length > 0
  ) {
    return NextResponse.json(
      { errors: payload.detail.errors },
      { status: 422 },
    );
  }
  // A 422 in any other shape is something we did not expect. Say so, rather than
  // returning an empty set of field errors that the form would silently swallow.
  if (upstream.status === 422) {
    return NextResponse.json(
      {
        error: "That message could not be read. Please check it and try again.",
      },
      { status: 422 },
    );
  }
  if (upstream.status === 429) {
    return NextResponse.json(
      {
        error:
          typeof payload.detail === "string"
            ? payload.detail
            : "Too many messages for now. Please try again in an hour.",
      },
      { status: 429 },
    );
  }
  return NextResponse.json(
    {
      error:
        "The message could not be sent. Please try again in a few minutes.",
    },
    { status: 502 },
  );
}
