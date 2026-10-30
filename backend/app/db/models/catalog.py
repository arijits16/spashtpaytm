"""Lenders, offers, KFS documents and the teach-back question bank (plan §6, §7.2-7.3).

These are the *facts* side of the product: every number the assistant is allowed
to say comes from here, which is what makes the Number Guard (§10.5) possible.
All lenders are fictional.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk


class Lender(Base, TimestampMixin):
    """A fictional NBFC or bank. The registration number and grievance contact
    are sample strings: a real KFS must carry them, so the PDF shows the field."""

    __tablename__ = "lenders"
    __table_args__ = (CheckConstraint("type IN ('NBFC', 'Bank')", name="type"),)

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    reg_no_sample: Mapped[str] = mapped_column(String(100), nullable=False)
    grievance_contact_sample: Mapped[str] = mapped_column(String(200), nullable=False)


class LoanOffer(Base, TimestampMixin):
    """One priced offer. Every money column is whole rupees except the rates.

    The derived columns (`emi`, `total_repay`, `apr`, ...) are stored rather than
    computed on read so a receipt can be verified years later against exactly
    the numbers the customer was shown; `journey/loan_math.py` asserts they
    match the formulae (§7.2).
    """

    __tablename__ = "loan_offers"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    lender_id: Mapped[str] = mapped_column(ForeignKey("lenders.id"), nullable=False, index=True)
    product: Mapped[str] = mapped_column(String(40), nullable=False, server_default="personal_loan")

    principal: Mapped[int] = mapped_column(Integer, nullable=False)
    tenure_months: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_pa: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    rate_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="reducing")

    processing_fee: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    gst_on_fee: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    emi: Mapped[int] = mapped_column(Integer, nullable=False)
    total_repay: Mapped[int] = mapped_column(Integer, nullable=False)
    total_interest: Mapped[int] = mapped_column(Integer, nullable=False)

    # 12x the monthly IRR of (net disbursed, then 12 EMIs). This is the number
    # that makes "lowest rate" and "cheapest" come apart - the demo's insight.
    apr: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)

    late_fee: Mapped[int] = mapped_column(Integer, nullable=False)
    foreclosure_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    cooling_off_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")

    # Never pre-selected anywhere in the product (§7.2).
    insurance_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    insurance_premium: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    kfs_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("kfs_documents.id", use_alter=True), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class KfsDocument(Base, TimestampMixin):
    """A Key Fact Statement: the PDF, its SHA-256 and the machine-readable facts.

    The hash is check #4 of receipt verification (§11.3): swapping the PDF after
    the fact breaks the receipt.
    """

    __tablename__ = "kfs_documents"
    __table_args__ = (
        CheckConstraint("source IN ('seed', 'sarvam_docai')", name="source"),
        CheckConstraint("status IN ('draft', 'verified', 'active', 'retired')", name="status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    lender_id: Mapped[str] = mapped_column(ForeignKey("lenders.id"), nullable=False, index=True)

    # Plain string, not an FK: loan_offers.kfs_document_id points back here and
    # a mutual FK pair makes seeding order painful for no benefit.
    offer_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    version: Mapped[str] = mapped_column(String(20), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    # The only numbers the assistant may speak about this loan (§10.5).
    facts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    verified_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="seed")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")

    # The raw extraction (phase 11): which engine read the file, the per-field
    # confidence, the job id. Kept out of `facts` on purpose - `facts` is the
    # Number Guard's allow-list, and a confidence score is not a number anybody
    # may say to a customer.
    extraction: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    # The publish proposal awaiting review: generated questions and explanation
    # lines in all three languages, each with its Number Guard verdict (§11).
    generated: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(200), nullable=True)


class KfsClause(Base, TimestampMixin):
    """One clause of a KFS, searchable. `tsv` is maintained by a DB trigger so
    an insert from anywhere (seed, Phase 11 ingestion) stays searchable."""

    __tablename__ = "kfs_clauses"

    id: Mapped[uuid.UUID] = uuid_pk()
    kfs_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kfs_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clause_key: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    text_en: Mapped[str] = mapped_column(Text, nullable=False)
    tsv: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)


class TeachbackQuestion(Base, TimestampMixin):
    """A question from the §7.3 bank, in all three languages.

    `{LATE_FEE}`-style placeholders in `prompt`, `options` and `reexplain` are
    filled from the selected offer's KFS facts by `journey/teachback.py`, so one
    seeded row works for every offer and no number is ever hard-coded in text.
    """

    __tablename__ = "teachback_questions"
    __table_args__ = (CheckConstraint("source IN ('seed', 'generated')", name="source"),)

    id: Mapped[str] = mapped_column(String(60), primary_key=True)

    # Which KFS fact this question tests. Drives the per-question pass-rate
    # chart on the dashboard (§12): a low rate means the KFS wording is poor.
    kfs_fact_key: Mapped[str] = mapped_column(String(60), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    prompt: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    reexplain: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Keywords that grade a free-form spoken answer before the LLM is asked.
    rubric: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # 'seed' or 'generated' (phase 11). A generated set is tied to the document
    # it was written from, so publishing a new KFS can swap the questions and a
    # rollback can put the seeded three back.
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="seed")
    kfs_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("kfs_documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
