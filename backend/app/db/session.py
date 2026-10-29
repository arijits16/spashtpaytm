"""SQLAlchemy engine and session factory.

The journey engine is short-transaction and request-scoped, so a synchronous
engine with a modest pool is the simple, reliable choice (plan rule 15). Sarvam
calls are async and happen outside the DB transaction.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

log = logging.getLogger(__name__)

engine: Engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # a laptop that slept must not serve a dead connection
    pool_size=5,
    max_overflow=10,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db() -> tuple[bool, str]:
    """Cheap liveness probe for `/api/health`. Returns (ok, detail)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - health must report, never raise
        log.warning("db health check failed", extra={"error_type": type(exc).__name__})
        return False, type(exc).__name__
