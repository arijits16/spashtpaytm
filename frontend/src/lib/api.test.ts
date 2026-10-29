import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, setAuthTokenProvider } from "@/lib/api";

/** The URL the spy was called with, as a string - typed, so no base-to-string. */
function calledUrl(spy: ReturnType<typeof vi.fn<typeof fetch>>): string {
  const input = spy.mock.calls[0]?.[0];
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  if (input instanceof Request) return input.url;
  throw new Error("fetch was not called");
}

function mockFetch(response: Partial<Response> & { jsonBody?: unknown }) {
  const { jsonBody, ...rest } = response;
  const fake = {
    ok: true,
    status: 200,
    statusText: "OK",
    json: () => Promise.resolve(jsonBody),
    ...rest,
  } as Response;
  const spy = vi.fn<typeof fetch>().mockResolvedValue(fake);
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
  setAuthTokenProvider(() => Promise.resolve(null));
});

describe("apiFetch", () => {
  it("prefixes the API base and parses JSON", async () => {
    const spy = mockFetch({ jsonBody: { status: "ok" } });

    await expect(apiFetch("/health")).resolves.toEqual({ status: "ok" });
    expect(calledUrl(spy)).toBe("/api/health");
  });

  it("attaches the bearer token when one is available", async () => {
    const spy = mockFetch({ jsonBody: {} });
    setAuthTokenProvider(() => Promise.resolve("id-token-123"));

    await apiFetch("/me");

    const headers = (spy.mock.calls[0]?.[1]?.headers as Headers) ?? new Headers();
    expect(headers.get("Authorization")).toBe("Bearer id-token-123");
  });

  it("sends no Authorization header when signed out", async () => {
    const spy = mockFetch({ jsonBody: {} });

    await apiFetch("/health");

    const headers = (spy.mock.calls[0]?.[1]?.headers as Headers) ?? new Headers();
    expect(headers.has("Authorization")).toBe(false);
  });

  it("keeps tokens and data out of the URL", async () => {
    const spy = mockFetch({ jsonBody: {} });
    setAuthTokenProvider(() => Promise.resolve("secret-token"));

    await apiFetch("/me");

    expect(calledUrl(spy)).not.toContain("secret-token");
  });

  it("raises ApiError carrying the status and FastAPI detail", async () => {
    mockFetch({
      ok: false,
      status: 409,
      statusText: "Conflict",
      jsonBody: { detail: "teach-back not passed" },
    });

    await expect(apiFetch("/journeys/x/turn", { method: "POST", body: {} })).rejects.toThrow(
      ApiError,
    );
    await expect(apiFetch("/journeys/x/turn", { method: "POST" })).rejects.toMatchObject({
      status: 409,
      detail: "teach-back not passed",
    });
  });

  it("falls back to statusText when the error body is not JSON", async () => {
    mockFetch({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.reject(new Error("not json")),
    });

    await expect(apiFetch("/health")).rejects.toMatchObject({
      status: 500,
      detail: "Internal Server Error",
    });
  });
});
