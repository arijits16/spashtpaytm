"""The `users` table (build plan section 6).

One row per Firebase account. `persona_id` stays a plain nullable string until
phase 2 adds the `personas` table and the foreign key.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# The three languages the journey supports (plan section 8.2).
DEFAULT_LANGUAGE = "mr-IN"
SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"mr-IN", "hi-IN", "en-IN"})


class User(Base, TimestampMixin):
    """A signed-in customer or admin.

    Nothing here is secret: the Firebase UID is an opaque identifier, and the
    name/email/photo come from the Google profile the user consented to share.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "preferred_language IN ('mr-IN', 'hi-IN', 'en-IN')",
            name="preferred_language",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Stable Firebase identifier - the join key for every request.
    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)

    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    preferred_language: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=DEFAULT_LANGUAGE
    )

    # Phase 2 turns this into a FK to personas.id; nullable until then.
    persona_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Derived from DASHBOARD_ADMIN_EMAILS on every login, never set by a client.
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.id} admin={self.is_admin}>"
