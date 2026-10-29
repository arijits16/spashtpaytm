"""FastAPI application factory for the Spasht backend.

Routers are mounted under `/api`; the Vite dev server proxies `/api` to port 8000,
so the phone needs a single HTTPS tunnel and there is no CORS in development.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.config import settings
from app.logging import configure_logging

log = logging.getLogger(__name__)

API_PREFIX = "/api"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown. Background jobs (rescue agent) attach here in phase 9."""
    configure_logging("DEBUG" if settings.is_dev else "INFO")
    log.info(
        "spasht backend starting",
        extra={
            "env": settings.app_env,
            "version": settings.app_version,
            "sarvam": "configured" if settings.sarvam_configured else "demo",
            "demo_mode": settings.demo_mode,
        },
    )
    yield
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

    # In dev the Vite proxy makes requests same-origin; CORS is the escape hatch
    # for a directly-opened backend and for the tunnel in phase 12.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Demo-User"],
    )

    app.include_router(health.router, prefix=API_PREFIX)
    return app


app = create_app()
