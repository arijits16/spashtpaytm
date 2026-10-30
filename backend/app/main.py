"""FastAPI application factory for the Spasht backend.

One backend serves three clients (build plan section 3): the native iPhone app
over the ngrok tunnel, the laptop website through the Vite `/api` proxy, and a
judge's phone browser hitting the public receipt page. Routers are mounted under
`/api`; the public receipt page (phase 6) will sit at `/r/{receiptNo}`.

Middleware order matters and is asserted by tests. Starlette runs middleware in
reverse registration order, so the list below is written outermost-last:

    request id  ->  security headers  ->  CORS  ->  body limit  ->  routes

The request id is set first so every log line and every error body can name it,
and the security headers wrap CORS so that even a rejected pre-flight carries
them.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    audio,
    dashboard,
    health,
    journeys,
    kfs,
    ledger,
    me,
    receipts,
    rescue,
    voice,
)
from app.config import settings
from app.errors import install_error_handlers
from app.logging import configure_logging
from app.rescue import scheduler as rescue_scheduler
from app.security.bodylimit import BodySizeLimitMiddleware
from app.security.headers import SecurityHeadersMiddleware
from app.security.request_id import RequestIdMiddleware
from app.web import public_receipt

log = logging.getLogger(__name__)

API_PREFIX = "/api"

# Headers a client may send. `X-Demo-User` / `X-Demo-Key` are the dev-only demo
# session (section 13.2); they are listed so the website can use demo admin in
# dev. The native app is not subject to CORS at all.
ALLOWED_REQUEST_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Demo-User",
    "X-Demo-Key",
    "X-Request-ID",
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown, including the rescue agent's background loop.

    The loop is an in-process task on the app's own event loop (plan section 4):
    one process, no broker, and it dies with the backend rather than outliving
    it. It is cancelled on shutdown and awaited, so a tick that is mid-query
    finishes or rolls back instead of leaving a session open.
    """
    configure_logging("DEBUG" if settings.is_dev else "INFO")
    log.info(
        "spasht backend starting",
        extra={
            "env": settings.app_env,
            "version": settings.app_version,
            "sarvam": "configured" if settings.sarvam_configured else "demo",
            "demo_mode": settings.demo_mode,
            "demo_auth": settings.demo_auth_allowed,
        },
    )

    # Disabled in tests, where a loop ticking against the same database would
    # create rescue tasks underneath assertions that counted them.
    rescue_task: asyncio.Task[None] | None = None
    if settings.rescue_agent_enabled:
        rescue_task = asyncio.create_task(
            rescue_scheduler.run_forever(settings), name="rescue-agent"
        )

    try:
        yield
    finally:
        if rescue_task is not None:
            rescue_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await rescue_task
        log.info("spasht backend stopped")


def create_app() -> FastAPI:
    """Build the ASGI app. Kept as a factory so tests can make a fresh instance."""
    app = FastAPI(
        title="Spasht API",
        version=settings.app_version,
        description=(
            "Backend for Spasht - a voice-first loan clarity co-pilot. "
            "Concept demo for the Paytm Build for India AI Hackathon. "
            "Synthetic data only."
        ),
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs" if settings.is_dev else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if settings.is_dev else None,
    )

    # Innermost first (see the module docstring for the resulting order).
    app.add_middleware(BodySizeLimitMiddleware)

    # The native app does not use CORS; this exists only for the website, so the
    # allowlist is exactly `CORS_ORIGINS` and never `*` (section 13.4).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=ALLOWED_REQUEST_HEADERS,
        expose_headers=["X-Request-ID", "Retry-After"],
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    install_error_handlers(app)

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(me.router, prefix=API_PREFIX)
    app.include_router(journeys.router, prefix=API_PREFIX)
    app.include_router(voice.router, prefix=API_PREFIX)
    app.include_router(audio.router, prefix=API_PREFIX)
    app.include_router(kfs.router, prefix=API_PREFIX)
    app.include_router(receipts.router, prefix=API_PREFIX)
    app.include_router(ledger.router, prefix=API_PREFIX)
    app.include_router(dashboard.router, prefix=API_PREFIX)
    app.include_router(rescue.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)

    # Deliberately *not* under /api: it is a page a person opens, and the QR
    # code printed on a receipt is shorter for it (plan section 11.6).
    app.include_router(public_receipt.router)
    return app


app = create_app()
