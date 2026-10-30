"""Request body size limits (build plan section 13.5).

Two limits: 64 KB for JSON and 2 MB for an audio upload. Enforced as middleware
rather than per route, because by the time a route function runs, the body has
already been read into memory - which is exactly what the limit exists to
prevent.

`Content-Length` is checked first (cheap, and honest clients always send it).
A chunked request without it is counted as it streams, so a body that lies about
its size still cannot exhaust memory.
"""

from __future__ import annotations

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import error_response
from app.security.request_id import get_request_id

log = logging.getLogger(__name__)

JSON_BODY_LIMIT = 64 * 1024  # 64 KB
AUDIO_BODY_LIMIT = 2 * 1024 * 1024  # 2 MB (section 10.1)

# Only these paths may send the larger body. Suffix matching keeps it working
# for `/api/journeys/{id}/voice` without parsing the path parameters.
_UPLOAD_SUFFIXES = ("/voice", "/kfs/upload")


def limit_for_path(path: str) -> int:
    """The body limit that applies to a path."""
    if any(path.endswith(suffix) for suffix in _UPLOAD_SUFFIXES):
        return AUDIO_BODY_LIMIT
    return JSON_BODY_LIMIT


class BodySizeLimitMiddleware:
    """Reject oversized bodies with 413 before they are buffered.

    Written as raw ASGI, not `BaseHTTPMiddleware`: the latter materialises the
    whole body to hand it on, so a streaming check there would be too late.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return

        limit = limit_for_path(scope.get("path", ""))

        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await self._reject(scope, send, limit, declared)
            return

        received = 0
        too_large = False

        async def counting_receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    too_large = True
                    # Stop the stream rather than keep buffering a body we have
                    # already decided to refuse.
                    return {"type": "http.disconnect"}
            return message

        await self.app(scope, counting_receive, send)

        if too_large:
            log.info(
                "request body over limit",
                extra={"path": scope.get("path"), "limit": limit, "request_id": get_request_id()},
            )

    async def _reject(self, scope: Scope, send: Send, limit: int, declared: int) -> None:
        log.info(
            "request body rejected on content-length",
            extra={
                "path": scope.get("path"),
                "limit": limit,
                "declared": declared,
                "request_id": get_request_id(),
            },
        )
        response = error_response(
            "upload_too_large",
            f"Request body is larger than the {limit // 1024} KB limit.",
            413,
            get_request_id(),
        )
        await response(scope, _empty_receive, send)


def _declared_length(scope: Scope) -> int | None:
    """Parse `Content-Length`, treating a malformed value as absent."""
    for name, value in scope.get("headers", ()):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _empty_receive() -> Message:
    """A receive channel for a response sent without reading the request."""
    return {"type": "http.disconnect"}
