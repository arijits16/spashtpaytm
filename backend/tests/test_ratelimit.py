"""Token-bucket rate limiting (build plan section 13.5).

The limiter is tested directly rather than through a route: the routes it
protects (`/voice`, `/turn`, OTP) arrive in phase 3, and the thing worth pinning
down now is the arithmetic - that a burst is allowed, that the bucket actually
empties, and that two identities never share a budget.
"""

from __future__ import annotations

import pytest

from app.errors import ApiError
from app.security.ratelimit import LIMITS, Limit, RateLimiter


@pytest.fixture()
def limiter() -> RateLimiter:
    return RateLimiter()


def test_a_first_request_is_always_allowed(limiter: RateLimiter) -> None:
    """A new identity starts with a full bucket, so nothing is denied cold."""
    assert limiter.check("turn", "user:new") == 0.0


def test_the_full_allowance_passes_then_the_next_is_denied(limiter: RateLimiter) -> None:
    allowance = LIMITS["voice"].requests

    for _ in range(allowance):
        assert limiter.check("voice", "user:sunita") == 0.0

    wait = limiter.check("voice", "user:sunita")
    assert wait > 0


def test_the_retry_hint_is_within_the_window(limiter: RateLimiter) -> None:
    """A 429 must not tell the app to wait longer than the window itself."""
    limit = LIMITS["voice"]
    for _ in range(limit.requests):
        limiter.check("voice", "user:sunita")

    wait = limiter.check("voice", "user:sunita")
    assert 0 < wait <= limit.window_seconds


def test_identities_have_separate_budgets(limiter: RateLimiter) -> None:
    """One noisy visitor must not throttle a customer mid-journey."""
    for _ in range(LIMITS["turn"].requests):
        limiter.check("turn", "ip:203.0.113.9")

    assert limiter.check("turn", "ip:203.0.113.9") > 0
    assert limiter.check("turn", "user:sunita") == 0.0


def test_limits_do_not_share_buckets(limiter: RateLimiter) -> None:
    """Exhausting /voice must leave the same user's /turn budget intact."""
    for _ in range(LIMITS["voice"].requests):
        limiter.check("voice", "user:sunita")

    assert limiter.check("voice", "user:sunita") > 0
    assert limiter.check("turn", "user:sunita") == 0.0


def test_the_bucket_refills_over_time(
    limiter: RateLimiter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Waiting a full window restores the whole allowance."""
    clock = {"now": 1_000.0}
    monkeypatch.setattr("app.security.ratelimit.time.monotonic", lambda: clock["now"])

    for _ in range(LIMITS["turn"].requests):
        limiter.check("turn", "user:sunita")
    assert limiter.check("turn", "user:sunita") > 0

    clock["now"] += LIMITS["turn"].window_seconds
    assert limiter.check("turn", "user:sunita") == 0.0


def test_enforce_raises_a_429_with_retry_after(limiter: RateLimiter) -> None:
    for _ in range(LIMITS["otp_verify"].requests):
        limiter.enforce("otp_verify", "journey:abc")

    with pytest.raises(ApiError) as excinfo:
        limiter.enforce("otp_verify", "journey:abc")

    error = excinfo.value
    assert error.code == "rate_limited"
    assert error.status_code == 429
    # Without this header the app has no idea when to try again.
    assert int(error.headers["Retry-After"]) >= 1


def test_otp_verify_matches_the_documented_policy() -> None:
    """Section 13.5 fixes this one precisely: 5 attempts per 10 minutes."""
    assert LIMITS["otp_verify"] == Limit(requests=5, window_seconds=600)


def test_reset_clears_state(limiter: RateLimiter) -> None:
    for _ in range(LIMITS["turn"].requests):
        limiter.check("turn", "user:sunita")
    assert limiter.check("turn", "user:sunita") > 0

    limiter.reset()
    assert limiter.check("turn", "user:sunita") == 0.0
