/**
 * The dashboard's live feed (build plan 12, phase 9).
 *
 * **Not `EventSource`.** The browser's own `EventSource` cannot set request
 * headers, which would force the Firebase ID token into the query string -
 * where it lands in access logs and browser history. So this is a `fetch`
 * reading `text/event-stream` and parsing the frames, which keeps the token in
 * an `Authorization` header where it belongs.
 *
 * **Polling is the fallback, not a failure mode.** A corporate proxy or a
 * flaky venue network will break a long-lived stream, and a dashboard that
 * silently stops updating during a demo is worse than one that refreshes every
 * few seconds. So a dropped stream falls back to polling and keeps trying to
 * reconnect in the background.
 */

import type { DashboardEvent, DashboardEventName } from "@/lib/types";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "/api";

/** How long to wait before reconnecting, growing to a ceiling. */
const RECONNECT_MIN_MS = 1_000;
const RECONNECT_MAX_MS = 15_000;

/** How often the polling fallback refreshes. */
export const POLL_INTERVAL_MS = 4_000;

export type ConnectionState = "connecting" | "live" | "polling";

interface StreamOptions {
  /** Resolves the auth header value, or null when signed out. */
  getAuth: () => Promise<Record<string, string>>;
  onEvent: (event: DashboardEvent) => void;
  onStateChange: (state: ConnectionState) => void;
  signal: AbortSignal;
}

/**
 * Hold a stream open, reconnecting for as long as `signal` is unaborted.
 *
 * Never throws: every failure path reports `polling` and retries. The caller is
 * a React effect, and an unhandled rejection there would be invisible.
 */
export async function streamDashboard(options: StreamOptions): Promise<void> {
  const { getAuth, onEvent, onStateChange, signal } = options;
  let backoff = RECONNECT_MIN_MS;

  while (!signal.aborted) {
    onStateChange("connecting");

    try {
      const headers = new Headers({ Accept: "text/event-stream" });
      for (const [key, value] of Object.entries(await getAuth())) {
        headers.set(key, value);
      }

      const response = await fetch(`${BASE_URL}/dashboard/stream`, {
        headers,
        signal,
        // A stream must not be served from cache, and `keepalive` would cap
        // the body size.
        cache: "no-store",
      });

      if (!response.ok || response.body === null) {
        throw new Error(`stream responded ${response.status}`);
      }

      onStateChange("live");
      // Reset only after a *successful* connect, so a flapping endpoint still
      // backs off rather than hammering.
      backoff = RECONNECT_MIN_MS;

      await readFrames(response.body, onEvent, signal);
    } catch (error) {
      if (signal.aborted) return;
      // Expected on a laptop that slept, a proxy timeout, or a dropped Wi-Fi.
      console.warn("[spasht] dashboard stream dropped; polling", error);
    }

    if (signal.aborted) return;

    onStateChange("polling");
    await sleep(backoff, signal);
    backoff = Math.min(RECONNECT_MAX_MS, backoff * 2);
  }
}

/**
 * Parse SSE frames out of a byte stream.
 *
 * Frames are separated by a blank line and can be split across chunks, so the
 * buffer is only consumed up to the last complete separator.
 */
async function readFrames(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: DashboardEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) return;

      buffer += decoder.decode(value, { stream: true });

      let separator = buffer.indexOf("\n\n");
      while (separator !== -1) {
        const frame = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);

        const parsed = parseFrame(frame);
        if (parsed) onEvent(parsed);

        separator = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/** One frame to an event, or null for a comment (`: heartbeat`). */
function parseFrame(frame: string): DashboardEvent | null {
  let name: string | null = null;
  const dataLines: string[] = [];

  for (const line of frame.split("\n")) {
    // A comment line. The backend sends these as heartbeats to stop a proxy
    // closing an idle connection.
    if (line.startsWith(":")) continue;

    if (line.startsWith("event:")) {
      name = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }

  if (name === null || dataLines.length === 0) return null;

  try {
    return {
      name: name as DashboardEventName,
      data: JSON.parse(dataLines.join("\n")) as Record<string, unknown>,
    };
  } catch {
    console.warn("[spasht] could not parse an event payload");
    return null;
  }
}

/** Abortable sleep, so a reconnect wait does not outlive the component. */
function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
  });
}
