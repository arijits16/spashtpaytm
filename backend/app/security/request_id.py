"""Request IDs (build plan section 8.1: "every response carries X-Request-ID").

A `ContextVar` rather than request state, so a log line emitted deep inside the
journey engine can name its request without every function taking a `Request`
parameter. That is what makes a failure during the demo traceable: the app shows
the id, and `grep` finds every line that produced it.

An inbound `X-Request-ID` is accepted (the ngrok agent and curl both set it) but
sanitised first - it ends up in a response header and in logs, so a caller must
not be able to inject control characters or an unbounded string.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 64

# Conservative: the characters a tracing id legitimately needs, nothing more.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """The current request's id, or `-` outside a request."""
    return _request_id.get()


def new_request_id() -> str:
    """A fresh id. Short enough to read aloud while debugging."""
    return uuid.uuid4().hex[:16]


def _accept_inbound(value: str | None) -> str:
    """Reuse a caller-supplied id when it is safe, otherwise mint one."""
    if value and _SAFE_REQUEST_ID.match(value):
        return value
    return new_request_id()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind an id to the request context and echo it on the response."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = _accept_inbound(request.headers.get(REQUEST_ID_HEADER))
        token = _request_id.set(request_id)
        try:
            response = await call_next(request)
        finally:
            # Reset even on failure: the error handlers read the id, and ASGI
            # workers are reused across requests.
            _request_id.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
