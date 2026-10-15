/**
 * Payment providers' notifications, passed to the engine untouched.
 *
 * The engine is not on the internet; this route is how a provider reaches it. The body must go
 * through byte for byte, because the provider's signature is computed over the exact bytes it
 * sent, and the engine is what checks that signature. This route trusts nothing and decides
 * nothing.
 */

import { NextResponse } from "next/server";
import { ENGINE_URL } from "@/lib/session";

const SIGNATURE_HEADER: Record<string, string> = {
  stripe: "stripe-signature",
  paystack: "x-paystack-signature",
};

export async function POST(
  request: Request,
  { params }: { params: Promise<{ provider: string }> },
) {
  const { provider } = await params;
  const header = SIGNATURE_HEADER[provider];
  if (!header) {
    return NextResponse.json(
      { detail: { code: "not_found" } },
      { status: 404 },
    );
  }
  const raw = await request.arrayBuffer();
  const signature = request.headers.get(header);
  let upstream: Response;
  try {
    upstream = await fetch(`${ENGINE_URL}/premium/webhook/${provider}`, {
      method: "POST",
      headers: {
        "content-type":
          request.headers.get("content-type") ?? "application/json",
        ...(signature ? { [header]: signature } : {}),
      },
      body: raw,
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
    });
  } catch {
    // 503 makes the provider retry later, which is what we want.
    return NextResponse.json({ ok: false }, { status: 503 });
  }
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}
