"""users table

The first real table (build plan section 6). `persona_id` is a plain nullable
string here; phase 2 adds `personas` and turns it into a foreign key.

Revision ID: 0002_users
Revises: 0001_baseline
Create Date: 2026-10-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_users"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("firebase_uid", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("photo_url", sa.String(length=1024), nullable=True),
        sa.Column(
            "preferred_language",
            sa.String(length=10),
            server_default="mr-IN",
            nullable=False,
        ),
        # Becomes a FK to personas.id in phase 2.
        sa.Column("persona_id", sa.String(length=50), nullable=True),
        sa.Column("is_admin", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        # Defence in depth: the API validates the language too, but a buggy
        # endpoint must not be able to store an unsupported locale.
        sa.CheckConstraint(
            "preferred_language IN ('mr-IN', 'hi-IN', 'en-IN')",
            name=op.f("ck_users_preferred_language"),
        ),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
    op.create_index(op.f("ix_users_firebase_uid"), "users", ["firebase_uid"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_firebase_uid"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
