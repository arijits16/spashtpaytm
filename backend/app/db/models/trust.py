"""The receipt ledger (plan §6, §11).

A receipt is a hash-chained, Ed25519-signed snapshot of what the customer was
shown, understood and agreed to. The chain means a single altered row breaks
every receipt after it; the signature means a row inserted straight into
Postgres cannot be made to verify.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, uuid_pk

# The chain's genesis `prev_hash` (§11.2).
GENESIS_HASH = "0" * 64


class Receipt(Base):
    """Append-only. One per completed journey.

    `payload_canonical` is stored verbatim rather than re-serialised on read:
    verification must hash exactly the bytes that were signed, and any change in
    how Python orders or escapes JSON would otherwise silently break every old
    receipt.
    """

    __tablename__ = "receipts"
    __table_args__ = (Index("ix_receipts_created", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    receipt_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)

    # Position in the chain. Unique and gap-free, assigned under a row lock on
    # `ledger_head` so parallel appends cannot interleave (§11.2).
    seq: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)

    journey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="RESTRICT"), unique=True, nullable=False
    )

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_canonical: Mapped[str] = mapped_column(Text, nullable=False)

    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(50), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LedgerHead(Base):
    """The single-row tip of the chain, locked `FOR UPDATE` during an append.

    One row, enforced by a CHECK on the primary key: a second head would mean
    two chains.
    """

    __tablename__ = "ledger_head"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    last_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    last_hash: Mapped[str] = mapped_column(String(64), nullable=False, server_default=GENESIS_HASH)


class SigningKey(Base):
    """Public half of a receipt signing key, served at `/api/public-keys`.

    Old keys stay with `active = false` so receipts signed before a rotation
    still verify.
    """

    __tablename__ = "signing_keys"

    key_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    public_key_b64: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DailyAnchor(Base):
    """A day's Merkle root over that day's receipt hashes (§11.4).

    In production this would be published somewhere we do not control, which is
    what makes a whole-table rewrite detectable rather than merely hard.
    """

    __tablename__ = "daily_anchors"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    merkle_root: Mapped[str] = mapped_column(String(64), nullable=False)
    receipt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
