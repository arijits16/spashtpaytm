"""Security response headers (build plan section 13.10).

Applied to **every** response, including errors, so there is no route that can
forget them. The public receipt page (`/r/*`, phase 6) needs a stricter CSP than
the API, so `csp_for_path` keeps that decision in one place rather than letting
each router invent its own policy.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Section 13.10. `Permissions-Policy` denies the three capabilities a browser
# might otherwise grant on our origin - the native app asks iOS for the mic, not
# a web page, so nothing we serve needs them.
BASE_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# The API serves JSON only, so nothing may be loaded or framed from it at all.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

# Section 11.6: the server-rendered receipt page has inline styles and data: QR
# images, and nothing else - no scripts, no fonts, no third-party anything.
PUBLIC_PAGE_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
    "frame-ancestors 'none'; base-uri 'none'"
)

# FastAPI's interactive docs load Swagger UI from a CDN, so the strict API CSP
# would blank the page. Dev-only route, so a relaxed policy is acceptable.
_DOCS_PATHS = frozenset({"/api/docs", "/api/redoc", "/api/openapi.json"})
_DOCS_CSP = (
    "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'"
)


def csp_for_path(path: str) -> str:
    """Pick the Content-Security-Policy for a request path."""
    if path in _DOCS_PATHS:
        return _DOCS_CSP
    if path == "/r" or path.startswith("/r/"):
        return PUBLIC_PAGE_CSP
    return API_CSP


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add the section 13.10 headers, and strip the server banner."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)

        for name, value in BASE_HEADERS.items():
            # setdefault semantics: a route that deliberately set its own value
            # (a PDF wanting to be framed in the app's viewer, say) keeps it.
            response.headers.setdefault(name, value)

        response.headers.setdefault("Content-Security-Policy", csp_for_path(request.url.path))

        # Only meaningful behind the tunnel; `X-Forwarded-Proto` is trusted
        # because uvicorn accepts forwarded headers from 127.0.0.1 only.
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        # Don't advertise the stack. This catches a `Server` header set inside
        # the app; uvicorn adds its own *after* the ASGI layer, where middleware
        # cannot reach it, so the Makefile also passes `--no-server-header`.
        if "server" in response.headers:
            del response.headers["server"]

        return response
