"""`GET /api/health` - the one route the frontend shell calls on load.

Shape is fixed by the build plan (section 8.1):
`{status, db, sarvam: "configured" | "demo", version}`
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.db.session import check_db

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health payload. Deliberately free of anything secret or personal."""

    status: Literal["ok", "degraded"]
    db: str
    sarvam: Literal["configured", "demo"]
    version: str
    env: str
    demoMode: bool


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report app, DB and Sarvam readiness.

    Always returns 200 so the frontend can render a precise banner instead of a
    generic network failure; `status` carries the verdict.
    """
    db_ok, db_detail = check_db()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db="ok" if db_ok else f"error: {db_detail}",
        sarvam="configured" if settings.sarvam_configured else "demo",
        version=settings.app_version,
        env=settings.app_env,
        demoMode=settings.demo_mode,
    )
