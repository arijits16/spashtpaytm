/**
 * The hook behind every live view (build plan 12, phase 9).
 *
 * It owns one SSE connection for the whole dashboard and re-fetches the data a
 * given page cares about when a relevant event arrives. One connection rather
 * than one per page, because the backend's bus fans out to subscribers and four
 * open pages would otherwise mean four streams and four heartbeats.
 *
 * Refetching on an event, rather than applying the event's payload as a patch,
 * is a deliberate trade: one extra request per change, in exchange for the
 * screen always showing what the backend actually holds. A dashboard that
 * accumulates patches can drift from the database, and this one is read by
 * someone checking compliance.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/lib/authContext";
import { POLL_INTERVAL_MS, streamDashboard, type ConnectionState } from "@/lib/sse";
import type { DashboardEventName } from "@/lib/types";

interface Options<T> {
  /** Fetches the view's data. Must be stable (wrap it in `useCallback`). */
  fetcher: (signal: AbortSignal) => Promise<T>;
  /** Which events should trigger a refetch. */
  events: DashboardEventName[];
  /** Also refetch on this interval, as a safety net. */
  pollMs?: number;
}

interface LiveResult<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  connection: ConnectionState;
  /** Increments on every event received, so views can flash a row. */
  pulse: number;
  refresh: () => void;
}

export function useLiveDashboard<T>({ fetcher, events, pollMs }: Options<T>): LiveResult<T> {
  const { authHeaders } = useAuth();

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [pulse, setPulse] = useState(0);

  // The caller passes a fresh array each render, so the set is memoised on its
  // *contents* rather than on the array identity - otherwise the stream effect
  // below would tear down and reconnect on every render.
  const eventKey = events.join(",");
  const interesting = useMemo(() => new Set<string>(eventKey.split(",")), [eventKey]);

  // Mirrored into a ref so the stream effect can read the current set without
  // listing it as a dependency, which would reconnect whenever it changed.
  const interestingRef = useRef(interesting);
  useEffect(() => {
    interestingRef.current = interesting;
  }, [interesting]);

  const [refreshToken, setRefreshToken] = useState(0);
  const refresh = useCallback(() => setRefreshToken((value) => value + 1), []);

  // --- the data -------------------------------------------------------------

  useEffect(() => {
    // A `cancelled` flag, not `controller.abort()`, guards a stale result.
    // Actually aborting here tears down the in-flight request through Vite's
    // dev proxy, and React 19 StrictMode's mount -> cleanup -> mount replay
    // does exactly that within milliseconds on every first load - which the
    // proxy's pooled connection sometimes surfaces as a transient 503 on the
    // very next request (reproduced: a tab's first load intermittently 503s
    // two or three times before the data appears). Letting the stale request
    // finish in the background and simply ignoring its result costs nothing
    // and removes that flakiness.
    const controller = new AbortController();
    let cancelled = false;

    void (async () => {
      try {
        const next = await fetcher(controller.signal);
        if (cancelled) return;
        setData(next);
        setError(null);
      } catch (cause) {
        if (cancelled) return;
        setError(cause instanceof Error ? cause.message : "Could not load this view.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [fetcher, refreshToken]);

  // --- the stream -----------------------------------------------------------

  useEffect(() => {
    const controller = new AbortController();

    void streamDashboard({
      getAuth: authHeaders,
      onEvent: (event) => {
        if (!interestingRef.current.has(event.name)) return;
        setPulse((value) => value + 1);
        setRefreshToken((value) => value + 1);
      },
      onStateChange: setConnection,
      signal: controller.signal,
    });

    return () => controller.abort();
  }, [authHeaders]);

  // --- the safety net -------------------------------------------------------

  useEffect(() => {
    // While the stream is live, a slow poll catches anything the bus dropped
    // (it discards the oldest event for a slow subscriber). While polling, it
    // is the only thing keeping the view current.
    const interval = connection === "live" ? (pollMs ?? 30_000) : POLL_INTERVAL_MS;
    const timer = setInterval(() => setRefreshToken((value) => value + 1), interval);
    return () => clearInterval(timer);
  }, [connection, pollMs]);

  return { data, error, loading, connection, pulse, refresh };
}
