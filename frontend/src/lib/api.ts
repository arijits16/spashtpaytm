/**
 * Thin fetch wrapper for the Spasht backend.
 *
 * `/api` is proxied to FastAPI by the Vite dev server. The Firebase ID token is
 * attached in phase 1 via `setAuthTokenProvider`, so nothing here needs to know
 * about auth yet. Tokens and personal data never go in the URL (plan 13).
 */

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "/api";

/** Resolves the current auth header value, or null when signed out. */
type TokenProvider = () => Promise<string | null>;

let tokenProvider: TokenProvider = () => Promise.resolve(null);

/** Phase 1 installs the Firebase token provider here. */
export function setAuthTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider;
}

/** An error carrying the HTTP status, so callers can branch on 401/403/409. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

/**
 * Call the backend and parse the JSON response.
 *
 * @param path  Path below the API base, e.g. `/health`.
 * @throws ApiError on any non-2xx response.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = options;

  const headers = new Headers({ Accept: "application/json" });
  if (body !== undefined) headers.set("Content-Type", "application/json");

  const token = await tokenProvider();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    ...(signal ? { signal } : {}),
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response));
  }
  return (await response.json()) as T;
}

/** Pull FastAPI's `{detail: ...}` out of an error body without throwing again. */
async function readErrorDetail(response: Response): Promise<string> {
  try {
    const parsed: unknown = await response.json();
    if (parsed !== null && typeof parsed === "object" && "detail" in parsed) {
      const { detail } = parsed;
      if (typeof detail === "string") return detail;
      if (typeof detail === "number" || typeof detail === "boolean") return String(detail);
      return JSON.stringify(detail);
    }
    return response.statusText;
  } catch {
    return response.statusText;
  }
}

// --- health ------------------------------------------------------------------

/** Mirror of the backend `HealthResponse` (plan 8.1). Kept in sync by hand. */
export interface Health {
  status: "ok" | "degraded";
  db: string;
  sarvam: "configured" | "demo";
  version: string;
  env: string;
  demoMode: boolean;
}

export const getHealth = (signal?: AbortSignal): Promise<Health> =>
  apiFetch<Health>("/health", signal ? { signal } : {});
