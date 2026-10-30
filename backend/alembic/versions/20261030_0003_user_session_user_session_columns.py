"""user session columns

Adds `email_verified`, `session_kind` and `last_login_at` to `users`
(build plan v2 section 6, phase 1).

`email_verified` is what makes the admin allowlist meaningful: an address
nobody has proved they own must not open the compliance dashboard, however it
got onto the list.

Existing rows default to `email_verified = false`, which is the safe direction -
a current admin simply has to sign in again to be recognised.

Revision ID: 0003_user_session
Revises: 0002_users
Create Date: 2026-10-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_user_session"
down_revision: str | None = "0002_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("session_kind", sa.String(length=20), server_default="firebase", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Defence in depth, matching the Pydantic Literal on the API side.
    op.create_check_constraint(
        "session_kind",
        "users",
        "session_kind IN ('firebase', 'demo')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_session_kind"), "users", type_="check")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "session_kind")
    op.drop_column("users", "email_verified")
