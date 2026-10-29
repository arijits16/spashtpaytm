"""baseline

Empty starting point for the migration chain. Real tables arrive in phase 1
(users) and phase 2 (the rest of section 6, plus the append-only triggers).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-29
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Nothing to do: this revision only anchors the chain."""


def downgrade() -> None:
    """Nothing to undo."""
