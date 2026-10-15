/**
 * Calls from the browser to this site's own routes (`/api/auth/...`, `/api/engine/...`).
 *
 * Every result has the same shape, so a form never has to guess: `ok` and `data` on success,
 * `error` with a stable `code` and a message that is safe to show on failure.
 */

export interface ApiError {
  code: string;
  message: string;
}

export interface ApiResult<T> {
  ok: boolean;
  status: number;
  data: T | null;
  error: ApiError | null;
}

function toError(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as { code?: string; message?: string };
    if (d.message) return { code: d.code ?? "error", message: d.message };
  }
  // FastAPI validation errors are a list; show something human, not the structure.
  if (Array.isArray(detail)) {
    return {
      code: "invalid_input",
      message: "Some of what you entered is not valid. Please check it and try again.",
    };
  }
  if (status === 429) {
    return {
      code: "rate_limited",
      message: "Too many attempts. Please wait a few minutes and try again.",
    };
  }
  return {
    code: "error",
    message: "Something went wrong. Please try again.",
  };
}

export async function api<T = Record<string, unknown>>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<ApiResult<T>> {
  try {
    const response = await fetch(path, {
      method: options.method ?? (options.body !== undefined ? "POST" : "GET"),
      headers:
        options.body !== undefined
          ? { "content-type": "application/json" }
          : undefined,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      credentials: "same-origin",
      cache: "no-store",
    });
    const body = await response.json().catch(() => null);
    if (response.ok) {
      return { ok: true, status: response.status, data: body as T, error: null };
    }
    return {
      ok: false,
      status: response.status,
      data: null,
      error: toError(response.status, body),
    };
  } catch {
    return {
      ok: false,
      status: 0,
      data: null,
      error: {
        code: "offline",
        message: "Could not reach the site. Check your connection and try again.",
      },
    };
  }
}
