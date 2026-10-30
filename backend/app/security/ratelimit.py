"""In-memory token-bucket rate limiting (build plan section 13.5).

One process, one dict: the backend is a single uvicorn worker on a laptop, so a
shared store would be complexity with no benefit. In production this moves to
Redis, which is recorded as a residual risk in `docs/SECURITY.md`.

A token bucket rather than a fixed window because the demo is bursty: tapping
three quick replies in a second is legitimate and must not be throttled, while a
script hammering `/voice` must be. The bucket refills continuously, so a short
burst up to `capacity` is fine and the sustained rate is still `per` requests
per `window_seconds`.

Keys are the user id when signed in and the client IP otherwise, so one noisy
visitor cannot exhaust a signed-in customer's budget mid-journey.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from fastapi import Request

from app.errors import rate_limited


@dataclass(frozen=True, slots=True)
class Limit:
    """`requests` allowed per `window_seconds`, with a burst up to `burst`."""

    requests: int
    window_seconds: int
    burst: int | None = None

    @property
    def capacity(self) -> float:
        """Maximum tokens the bucket holds. Defaults to the full allowance."""
        return float(self.burst if self.burst is not None else self.requests)

    @property
    def refill_per_second(self) -> float:
        return self.requests / self.window_seconds


# The table in section 13.5. Routes name a limit instead of inventing numbers,
# so the policy is reviewable in one place.
LIMITS: dict[str, Limit] = {
    "voice": Limit(requests=20, window_seconds=60),
    "turn": Limit(requests=60, window_seconds=60),
    "otp_verify": Limit(requests=5, window_seconds=600),
    "verify_candidate": Limit(requests=20, window_seconds=60),
    "public": Limit(requests=60, window_seconds=60),
    "demo_auth": Limit(requests=60, window_seconds=60),
    "login": Limit(requests=30, window_seconds=60),
}


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


@dataclass
class RateLimiter:
    """Thread-safe token buckets keyed by `"<limit name>:<identity>"`."""

    _buckets: dict[str, _Bucket] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # Cleaning up on write keeps memory bounded without a background task.
    _last_sweep: float = 0.0
    _sweep_interval: float = 300.0

    def check(self, limit_name: str, identity: str, *, cost: float = 1.0) -> float:
        """Consume `cost` tokens.

        @returns Seconds to wait when the bucket is empty, else 0.0.
        """
        limit = LIMITS[limit_name]
        key = f"{limit_name}:{identity}"
        now = time.monotonic()

        with self._lock:
            self._maybe_sweep(now)
            bucket = self._buckets.get(key)

            if bucket is None:
                # A new identity starts full, so a first request is never denied.
                bucket = _Bucket(tokens=limit.capacity, updated_at=now)
                self._buckets[key] = bucket
            else:
                elapsed = now - bucket.updated_at
                bucket.tokens = min(
                    limit.capacity, bucket.tokens + elapsed * limit.refill_per_second
                )
                bucket.updated_at = now

            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return 0.0

            deficit = cost - bucket.tokens
            return deficit / limit.refill_per_second

    def enforce(self, limit_name: str, identity: str, *, cost: float = 1.0) -> None:
        """Raise `rate_limited` (429 + Retry-After) when over the limit."""
        wait = self.check(limit_name, identity, cost=cost)
        if wait > 0:
            raise rate_limited(int(wait) + 1)

    def reset(self) -> None:
        """Drop all state. Tests call this; nothing in the app does."""
        with self._lock:
            self._buckets.clear()
            self._last_sweep = 0.0

    def _maybe_sweep(self, now: float) -> None:
        """Forget buckets that have been full and idle long enough to matter.

        Called with the lock held.
        """
        if now - self._last_sweep < self._sweep_interval:
            return
        self._last_sweep = now
        cutoff = now - self._sweep_interval
        stale = [
            key
            for key, bucket in self._buckets.items()
            if bucket.updated_at < cutoff and bucket.tokens >= LIMITS[key.split(":", 1)[0]].capacity
        ]
        for key in stale:
            del self._buckets[key]


# One limiter per process. Imported directly by routes.
limiter = RateLimiter()


def client_identity(request: Request, user_id: str | None = None) -> str:
    """The rate-limit key: the user id when known, otherwise the client IP.

    `request.client.host` is already the real client address because uvicorn
    runs with `--forwarded-allow-ips 127.0.0.1`, so `X-Forwarded-For` is only
    honoured from the local ngrok agent (section 13.4). Reading the header here
    ourselves would let any caller spoof its identity.
    """
    if user_id:
        return f"user:{user_id}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"
