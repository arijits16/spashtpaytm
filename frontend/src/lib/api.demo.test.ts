import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch, setAuthTokenProvider, setDemoUser } from "@/lib/api";

/**
 * How the API client picks between a real bearer token and the dev demo header.
 * The precedence rule here must mirror the backend's (`app/deps.py`): a real
 * token always wins, and the demo header is only a fallback.
 */

function mockFetch() {
  const spy = vi.fn<typeof fetch>().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: "OK",
    json: () => Promise.resolve({}),
  } as Response);
  vi.stubGlobal("fetch", spy);
  return spy;
}

function headersOf(spy: ReturnType<typeof mockFetch>): Headers {
  return (spy.mock.calls[0]?.[1]?.headers as Headers) ?? new Headers();
}

/** The URL the spy was called with, as a string - typed, so no base-to-string. */
function calledUrl(spy: ReturnType<typeof mockFetch>): string {
  const input = spy.mock.calls[0]?.[0];
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  if (input instanceof Request) return input.url;
  throw new Error("fetch was not called");
}

afterEach(() => {
  vi.unstubAllGlobals();
  setAuthTokenProvider(() => Promise.resolve(null));
  setDemoUser(null);
});

describe("demo user header", () => {
  it("sends X-Demo-User when there is no token", async () => {
    const spy = mockFetch();
    setDemoUser("sunita");

    await apiFetch("/me");

    expect(headersOf(spy).get("X-Demo-User")).toBe("sunita");
  });

  it("prefers a real bearer token over the demo header", async () => {
    const spy = mockFetch();
    setDemoUser("sunita");
    setAuthTokenProvider(() => Promise.resolve("id-token-123"));

    await apiFetch("/me");

    const headers = headersOf(spy);
    expect(headers.get("Authorization")).toBe("Bearer id-token-123");
    expect(headers.has("X-Demo-User")).toBe(false);
  });

  it("stops sending the header once the demo user is cleared", async () => {
    setDemoUser("sunita");
    setDemoUser(null);
    const spy = mockFetch();

    await apiFetch("/me");

    expect(headersOf(spy).has("X-Demo-User")).toBe(false);
  });

  it("never puts the demo persona in the URL", async () => {
    const spy = mockFetch();
    setDemoUser("sunita");

    await apiFetch("/me");

    expect(calledUrl(spy)).toBe("/api/me");
  });
});
