"""kfs ingestion: extraction metadata and generated teach-back questions

Phase 11 adds an ingestion path next to the seeded one: an admin uploads a
lender's KFS PDF, Sarvam Document Intelligence (or `pdfplumber` offline) reads
the fields, a **human verifies them**, and publishing activates the document,
re-prices the offer from the verified facts and swaps in generated teach-back
questions.

Three things that path needs and the baseline schema has no room for:

1. **`kfs_documents.extraction`** - the raw extraction: which engine read the
   file, the per-field confidence, and the job id. Kept separate from `facts`
   because `facts` is the Number Guard's allow-list and the source of every
   `{PLACEHOLDER}`; mixing confidence scores into it would put numbers nobody
   may speak into the set of numbers the assistant may speak.
2. **`kfs_documents.generated`** - the proposal a publish produces before it is
   activated: teach-back questions and explanation lines in mr/hi/en, each with
   the Number Guard's verdict. Parked on the row so the "review" half of
   "generate -> guard -> review -> activate" is a real step a human performs
   against stored text rather than a preview that disappears on refresh.
3. **`original_filename` / `uploaded_by`** - provenance for an audit trail that
   has to answer "who put this in, and what was it called".
4. **`teachback_questions.kfs_document_id` + `source`** - so a generated set can
   be activated, reviewed and rolled back without touching the seeded three.

Revision ID: 0005_kfs_ingestion
Revises: 0004_schema
Create Date: 2026-10-31 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_kfs_ingestion"
down_revision: str | None = "0004_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "kfs_documents",
        sa.Column(
            "extraction",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "kfs_documents",
        sa.Column(
            "generated",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "kfs_documents", sa.Column("original_filename", sa.String(length=255), nullable=True)
    )
    op.add_column("kfs_documents", sa.Column("uploaded_by", sa.String(length=200), nullable=True))

    op.add_column(
        "teachback_questions",
        sa.Column("source", sa.String(length=20), server_default=sa.text("'seed'"), nullable=False),
    )
    op.add_column(
        "teachback_questions",
        sa.Column("kfs_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_teachback_questions_kfs_document_id_kfs_documents"),
        "teachback_questions",
        "kfs_documents",
        ["kfs_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_teachback_questions_kfs_document_id"),
        "teachback_questions",
        ["kfs_document_id"],
    )
    op.create_check_constraint("source", "teachback_questions", "source IN ('seed', 'generated')")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_teachback_questions_source"), "teachback_questions", type_="check")
    op.drop_index(op.f("ix_teachback_questions_kfs_document_id"), table_name="teachback_questions")
    op.drop_constraint(
        op.f("fk_teachback_questions_kfs_document_id_kfs_documents"),
        "teachback_questions",
        type_="foreignkey",
    )
    op.drop_column("teachback_questions", "kfs_document_id")
    op.drop_column("teachback_questions", "source")
    op.drop_column("kfs_documents", "uploaded_by")
    op.drop_column("kfs_documents", "original_filename")
    op.drop_column("kfs_documents", "generated")
    op.drop_column("kfs_documents", "extraction")
