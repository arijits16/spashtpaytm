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

/** The AuthProvider installs the Firebase `getIdToken()` call here. */
export function setAuthTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider;
}

/**
 * Dev-only demo identity, sent as `X-Demo-User` + `X-Demo-Key`.
 *
 * The backend honours it only when DEMO_AUTH=true, APP_ENV=dev, and the key
 * matches `DEMO_AUTH_KEY` in constant time (plan 13.2). Both headers are
 * required; the identity alone gets a 401. Pass null to clear.
 *
 * A real bearer token always takes precedence, on both sides.
 */
let demoUser: string | null = null;
let demoKey: string | null = null;

export function setDemoUser(persona: string | null, key: string | null = null): void {
  demoUser = persona;
  demoKey = key;
}

/**
 * An error carrying the HTTP status and the backend's `code`, so callers can
 * branch on 401/403 or on a specific code like `consent_locked`.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly code: string = "internal_error",
  ) {
    super(`API ${status} ${code}: ${detail}`);
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
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  } else if (demoUser && demoKey) {
    headers.set("X-Demo-User", demoUser);
    headers.set("X-Demo-Key", demoKey);
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    ...(signal ? { signal } : {}),
  });

  if (!response.ok) {
    const { code, message } = await readError(response);
    throw new ApiError(response.status, message, code);
  }
  return (await response.json()) as T;
}

/**
 * Pull the standard error envelope out of a response (plan 8.1):
 *
 *     {"error": {"code": "...", "message": "...", "requestId": "..."}}
 *
 * Falls back to the status text for anything that is not our backend - an ngrok
 * interstitial or a proxy error page.
 */
async function readError(response: Response): Promise<{ code: string; message: string }> {
  try {
    const parsed: unknown = await response.json();
    if (parsed !== null && typeof parsed === "object" && "error" in parsed) {
      const { error: envelope } = parsed;
      if (envelope !== null && typeof envelope === "object") {
        const { code, message } = envelope as { code?: unknown; message?: unknown };
        return {
          code: typeof code === "string" ? code : "internal_error",
          message: typeof message === "string" ? message : response.statusText,
        };
      }
    }
    return { code: "internal_error", message: response.statusText };
  } catch {
    return { code: "internal_error", message: response.statusText };
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

// --- me ----------------------------------------------------------------------

export type Lang = "mr-IN" | "hi-IN" | "en-IN";

/** The linked synthetic customer. Null for `demo-admin` (plan 8.2). */
export interface Persona {
  id: string;
  displayNameMasked: string | null;
  language: Lang | null;
  city: string | null;
  occupation: string | null;
  mobileMasked: string | null;
}

/**
 * Mirror of the backend `MeResponse` (plan 8.2) and of
 * `contracts/fixtures/me.json`, which a test decodes. Kept in sync by hand; the
 * fixture test is what catches it when it is not.
 */
export interface Me {
  uid: string;
  email: string | null;
  displayName: string | null;
  photoUrl: string | null;
  preferredLanguage: Lang;
  isAdmin: boolean;
  /** How this request authenticated. Drives the demo badge. */
  session: "firebase" | "demo";
  persona: Persona | null;
}

export const getMe = (signal?: AbortSignal): Promise<Me> =>
  apiFetch<Me>("/me", signal ? { signal } : {});

/** Update the profile. Today only the language is user-editable. */
export const updateMe = (patch: { preferredLanguage: Lang }): Promise<Me> =>
  apiFetch<Me>("/me", { method: "PATCH", body: patch });
