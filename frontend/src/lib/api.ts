/**
 * Thin fetch wrapper for the Spasht backend.
 *
 * `/api` is proxied to FastAPI by the Vite dev server. The Firebase ID token is
 * attached in phase 1 via `setAuthTokenProvider`, so nothing here needs to know
 * about auth yet. Tokens and personal data never go in the URL (plan 13).
 */

import type {
  Anchor,
  CandidateResult,
  JourneyDetail,
  JourneyRow,
  KfsDocumentDetail,
  KfsLibraryResponse,
  KfsPublishResponse,
  LedgerResponse,
  Overview,
  PublicKey,
  ReceiptDetail,
  ReceiptRow,
  RescueRow,
  VerifyResult,
} from "@/lib/types";

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

/** The auth headers, shared by the JSON, upload and blob paths. */
async function authHeaders(): Promise<Headers> {
  const headers = new Headers();
  const token = await tokenProvider();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  } else if (demoUser && demoKey) {
    headers.set("X-Demo-User", demoUser);
    headers.set("X-Demo-Key", demoKey);
  }
  return headers;
}

/**
 * POST a `multipart/form-data` body (the KFS upload, phase 11).
 *
 * `Content-Type` is deliberately not set: the browser has to add the multipart
 * boundary, and setting it by hand produces a body FastAPI cannot parse.
 */
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const headers = await authHeaders();
  headers.set("Accept", "application/json");

  const response = await fetch(`${BASE_URL}${path}`, { method: "POST", headers, body: form });
  if (!response.ok) {
    const { code, message } = await readError(response);
    throw new ApiError(response.status, message, code);
  }
  return (await response.json()) as T;
}

/**
 * Fetch binary content with the auth headers attached.
 *
 * Used for the KFS preview: the admin file route needs a bearer token or the
 * demo headers, and an `<iframe src>` cannot send either - so the bytes are
 * fetched here and handed to the iframe as an object URL.
 */
export async function apiBlob(path: string): Promise<Blob> {
  const response = await fetch(`${BASE_URL}${path}`, { headers: await authHeaders() });
  if (!response.ok) {
    const { code, message } = await readError(response);
    throw new ApiError(response.status, message, code);
  }
  return await response.blob();
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

// --- dashboard ---------------------------------------------------------------

/**
 * The admin-only dashboard endpoints (build plan 12).
 *
 * All of them are enforced server-side: the route guards on the website are a
 * convenience, and bypassing them gains a non-admin nothing but a 403.
 */

export const getOverview = (signal?: AbortSignal): Promise<Overview> =>
  apiFetch<Overview>("/dashboard/overview", signal ? { signal } : {});

export const getJourneys = (signal?: AbortSignal): Promise<JourneyRow[]> =>
  apiFetch<JourneyRow[]>("/dashboard/journeys", signal ? { signal } : {});

export const getJourneyDetail = (id: string, signal?: AbortSignal): Promise<JourneyDetail> =>
  apiFetch<JourneyDetail>(`/dashboard/journeys/${id}`, signal ? { signal } : {});

export const getDashboardReceipts = (signal?: AbortSignal): Promise<ReceiptRow[]> =>
  apiFetch<ReceiptRow[]>("/dashboard/receipts", signal ? { signal } : {});

export const getRescueTasks = (signal?: AbortSignal): Promise<RescueRow[]> =>
  apiFetch<RescueRow[]>("/dashboard/rescue-tasks", signal ? { signal } : {});

export const getLedger = (signal?: AbortSignal): Promise<LedgerResponse> =>
  apiFetch<LedgerResponse>("/ledger", signal ? { signal } : {});

export const getAnchors = (signal?: AbortSignal): Promise<Anchor[]> =>
  apiFetch<Anchor[]>("/ledger/anchors", signal ? { signal } : {});

export const getPublicKeys = (signal?: AbortSignal): Promise<PublicKey[]> =>
  apiFetch<PublicKey[]>("/public-keys", signal ? { signal } : {});

// --- receipts and the tamper demo --------------------------------------------

export const getReceipt = (no: string, signal?: AbortSignal): Promise<ReceiptDetail> =>
  apiFetch<ReceiptDetail>(`/receipts/${no}`, signal ? { signal } : {});

export const verifyReceipt = (no: string, signal?: AbortSignal): Promise<VerifyResult> =>
  apiFetch<VerifyResult>(`/receipts/${no}/verify`, signal ? { signal } : {});

/**
 * Verify an **edited copy** of a receipt (build plan 11.3).
 *
 * The database is never touched: the tamper demo's whole point is that the
 * edited copy fails while the stored receipt keeps verifying.
 */
export const verifyCandidate = (
  no: string,
  payload: Record<string, unknown>,
): Promise<CandidateResult> =>
  apiFetch<CandidateResult>(`/receipts/${no}/verify-candidate`, {
    method: "POST",
    body: { payload },
  });

// --- demo controls (dev only) ------------------------------------------------

export const resetDemo = (): Promise<{ reset: boolean; counts: Record<string, number> }> =>
  apiFetch("/admin/demo/reset", { method: "POST", body: {} });

export const createAbandonedJourney = (
  body: { personaId?: string; step?: string; idleSeconds?: number } = {},
): Promise<{ journeyId: string; step: string; idleSeconds: number }> =>
  apiFetch("/admin/demo/abandoned-journey", { method: "POST", body });

export const getPersonas = (
  signal?: AbortSignal,
): Promise<
  { id: string; displayNameMasked: string; language: string; city: string; occupation: string }[]
> => apiFetch("/admin/personas", signal ? { signal } : {});

export const switchPersona = (personaId: string): Promise<Me> =>
  apiFetch<Me>("/me/persona", { method: "POST", body: { personaId } });

// --- KFS ingestion (phase 11) ------------------------------------------------

export const getKfsLibrary = (signal?: AbortSignal): Promise<KfsLibraryResponse> =>
  apiFetch<KfsLibraryResponse>("/admin/kfs", signal ? { signal } : {});

export const getKfsDocument = (id: string, signal?: AbortSignal): Promise<KfsDocumentDetail> =>
  apiFetch<KfsDocumentDetail>(`/admin/kfs/${id}`, signal ? { signal } : {});

export function uploadKfs(
  file: File,
  offerId: string,
  version: string,
): Promise<KfsDocumentDetail> {
  const form = new FormData();
  form.append("file", file);
  form.append("offerId", offerId);
  form.append("version", version);
  return apiUpload<KfsDocumentDetail>("/admin/kfs/upload", form);
}

export const verifyKfs = (
  id: string,
  corrections: Record<string, string>,
): Promise<KfsDocumentDetail> =>
  apiFetch<KfsDocumentDetail>(`/admin/kfs/${id}/verify`, {
    method: "POST",
    body: { corrections },
  });

/** `confirm: false` generates and guards; `confirm: true` activates what was reviewed. */
export const publishKfs = (id: string, confirm: boolean): Promise<KfsPublishResponse> =>
  apiFetch<KfsPublishResponse>(`/admin/kfs/${id}/publish`, {
    method: "POST",
    body: { confirm },
  });
