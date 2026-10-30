"""The one door to Sarvam AI (build plan §10).

Every call - speech-to-text, text-to-speech, the LLM, document intelligence -
goes through this client, so the timeout policy, the retry policy, the error
taxonomy and the latency logging exist once.

**The key lives only here.** It is read from settings, sent as
`api-subscription-key`, and scrubbed out of anything that gets logged or raised
(§13.3): an API that echoes a bad key back in an error body must not be able to
put it in our logs.

**Failure is expected, not exceptional.** This runs on venue Wi-Fi. Two
consecutive failures flip the whole product into demo mode (§10.6), where
templates and cached audio carry the journey to the end. So the client's job on
failure is to fail *fast and legibly* rather than to keep trying.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

# §10.4 budgets: speech-to-text 1.5 s, text-to-speech 1 s, the LLM ~1.5 s. The
# read timeouts are deliberately generous versions of those - a call that
# overruns is worth waiting a moment for, and the engine has already shown
# `Thinking…` - but short enough that a hung connection cannot stall a turn.
_TIMEOUTS = {
    "stt": httpx.Timeout(connect=4.0, read=20.0, write=20.0, pool=4.0),
    "tts": httpx.Timeout(connect=4.0, read=15.0, write=10.0, pool=4.0),
    "llm": httpx.Timeout(connect=4.0, read=20.0, write=10.0, pool=4.0),
    # Offline generation (phase 11 ingestion): no customer is waiting, the
    # offline model reasons before it answers, and the reply is a whole
    # teach-back question in three languages. The 20 s live budget times out on
    # it every time, which looks like a broken model rather than a tight clock.
    "offline": httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0),
    "docai": httpx.Timeout(connect=10.0, read=120.0, write=60.0, pool=10.0),
}

# §10: one retry on 429 or 5xx, with jitter. One, not three: a customer is
# waiting, and a provider that failed twice is not going to succeed on the
# third attempt inside the latency budget.
_MAX_ATTEMPTS = 2
_BACKOFF_BASE = 0.4
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

# Two consecutive failures turn on demo mode (§10.6).
DEMO_MODE_FAILURE_THRESHOLD = 2


class SarvamError(Exception):
    """A Sarvam call failed.

    @param kind  'unconfigured' | 'timeout' | 'status' | 'transport' | 'malformed'
    """

    def __init__(self, kind: str, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status

    @property
    def is_retryable(self) -> bool:
        return self.kind in {"timeout", "transport"} or (
            self.status is not None and self.status in _RETRY_STATUSES
        )


@dataclass
class SarvamResult:
    """A successful response, with how long it took.

    The latency is returned rather than only logged because it is stored on
    `conversation_turns` (§10.4) - "the median voice turn was under 4 seconds"
    has to be a measurement, not a claim.
    """

    payload: dict[str, Any]
    latency_ms: int


class _HealthTracker:
    """Counts consecutive failures, to decide when demo mode turns on.

    Process-local and deliberately simple: one uvicorn worker on a laptop, and
    the question it answers ("is Sarvam working right now?") is about the last
    few seconds, not about history.
    """

    def __init__(self) -> None:
        self._consecutive_failures = 0
        self._lock = asyncio.Lock()

    async def record_success(self) -> None:
        async with self._lock:
            self._consecutive_failures = 0

    async def record_failure(self) -> int:
        async with self._lock:
            self._consecutive_failures += 1
            return self._consecutive_failures

    @property
    def should_use_demo_mode(self) -> bool:
        return self._consecutive_failures >= DEMO_MODE_FAILURE_THRESHOLD

    def reset(self) -> None:
        """Tests only."""
        self._consecutive_failures = 0


health = _HealthTracker()


class SarvamClient:
    """Async httpx client for `api.sarvam.ai`."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.sarvam_base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self._settings.sarvam_api_key)

    def scrub(self, text: str) -> str:
        """Remove the key from text before it is logged or raised."""
        key = self._settings.sarvam_api_key
        return text.replace(key, "[REDACTED]") if key else text

    async def post_json(
        self, path: str, body: dict[str, Any], *, kind: str = "llm"
    ) -> SarvamResult:
        """POST a JSON body."""
        return await self._send(path, kind=kind, json=body)

    async def post_multipart(
        self,
        path: str,
        *,
        files: dict[str, Any],
        data: dict[str, Any] | None = None,
        kind: str = "stt",
    ) -> SarvamResult:
        """POST a multipart form (audio upload, document upload)."""
        return await self._send(path, kind=kind, files=files, data=data or {})

    async def get_json(self, path: str, *, kind: str = "docai") -> SarvamResult:
        """GET a JSON response (document-intelligence polling)."""
        return await self._send(path, kind=kind, method="GET")

    async def _send(
        self,
        path: str,
        *,
        kind: str,
        method: str = "POST",
        json: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> SarvamResult:
        if not self.configured:
            # Not an error worth retrying: the key is absent and will stay
            # absent. The caller falls back to demo mode immediately.
            raise SarvamError("unconfigured", "SARVAM_API_KEY is not set")

        url = f"{self._base_url}{path}"
        headers = {"api-subscription-key": self._settings.sarvam_api_key}
        last_error: SarvamError | None = None

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            started = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUTS[kind]) as client:
                    response = await client.request(
                        method, url, headers=headers, json=json, files=files, data=data
                    )
                elapsed_ms = int((time.perf_counter() - started) * 1000)

                if response.status_code >= 400:
                    error = SarvamError(
                        "status",
                        f"{path} returned {response.status_code}: "
                        f"{self.scrub(response.text)[:200]}",
                        status=response.status_code,
                    )
                    if error.is_retryable and attempt < _MAX_ATTEMPTS:
                        last_error = error
                        await self._backoff(attempt)
                        continue
                    raise error

                try:
                    payload = response.json()
                except ValueError as exc:
                    raise SarvamError("malformed", f"{path} did not return JSON") from exc

                # No PII and no text: just which call, how long, how big.
                log.info(
                    "sarvam ok",
                    extra={
                        "path": path,
                        "kind": kind,
                        "latency_ms": elapsed_ms,
                        "attempt": attempt,
                    },
                )
                await health.record_success()
                return SarvamResult(payload=payload, latency_ms=elapsed_ms)

            except httpx.TimeoutException as exc:
                last_error = SarvamError("timeout", f"{path} timed out")
                if attempt < _MAX_ATTEMPTS:
                    await self._backoff(attempt)
                    continue
                raise last_error from exc

            except httpx.HTTPError as exc:
                last_error = SarvamError("transport", f"{path} failed: {type(exc).__name__}")
                if attempt < _MAX_ATTEMPTS:
                    await self._backoff(attempt)
                    continue
                raise last_error from exc

            except SarvamError:
                raise

            finally:
                if last_error is not None and attempt == _MAX_ATTEMPTS:
                    failures = await health.record_failure()
                    log.warning(
                        "sarvam failed",
                        extra={
                            "path": path,
                            "kind": last_error.kind,
                            "status": last_error.status,
                            "consecutive_failures": failures,
                        },
                    )

        raise last_error or SarvamError("transport", f"{path} failed")

    @staticmethod
    async def _backoff(attempt: int) -> None:
        """Sleep with jitter, so two retrying turns do not collide."""
        delay = _BACKOFF_BASE * attempt + random.uniform(0, 0.2)  # noqa: S311
        await asyncio.sleep(delay)


def client_for(settings: Settings) -> SarvamClient:
    """A client for these settings. Cheap to construct; httpx owns the pooling."""
    return SarvamClient(settings)


def demo_mode_active(settings: Settings) -> bool:
    """Whether to serve this turn from templates and cached audio (§10.6).

    True when explicitly switched on, when there is no key, or when Sarvam has
    just failed twice in a row. The response's `demoMode` flag comes from here,
    so the app's chip cannot disagree with what the backend is actually doing.
    """
    if settings.demo_mode or not settings.sarvam_api_key:
        return True
    return health.should_use_demo_mode
