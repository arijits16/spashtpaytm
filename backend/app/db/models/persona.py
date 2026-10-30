"""Synthetic customers and the mock data the prefill adapters return (plan §6, §7.1).

Everything in these tables is invented. The identifiers are format-correct but
fake (Aadhaar `XXXX XXXX 4821`, PAN `ABCPJ1234F`) so the UI can show a realistic
masked value without ever holding a real one.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk

# Document kinds DigiLocker mock can return (plan §6).
DOC_TYPES: frozenset[str] = frozenset({"aadhaar", "pan", "address_proof"})


class Persona(Base, TimestampMixin):
    """A synthetic borrower. `id` is a readable slug ('sunita'), not a UUID,
    because it appears in seed files, demo controls and the audit log."""

    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # The real name is only ever used to build the honorific the assistant
    # speaks; everything shown on screen or on a receipt uses the masked form.
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name_masked: Mapped[str] = mapped_column(String(200), nullable=False)

    # {"mr": "सुनीता", "hi": "सुनीता"} - used for `{NAME_HONORIFIC}` (§7.4).
    name_local: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    gender: Mapped[str] = mapped_column(String(10), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    dob: Mapped[date] = mapped_column(Date, nullable=False)

    city: Mapped[str] = mapped_column(String(100), nullable=False)
    locality: Mapped[str] = mapped_column(String(200), nullable=False)
    occupation: Mapped[str] = mapped_column(String(100), nullable=False)
    business_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="mr-IN")
    mobile_masked: Mapped[str] = mapped_column(String(32), nullable=False)

    # Whether a rescue call may be placed at all (§9, phase 10). `dnd` wins.
    consent_callbacks: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    dnd: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Persona {self.id}>"


class DigilockerRecord(Base, TimestampMixin):
    """What the DigiLocker mock adapter hands back for one document."""

    __tablename__ = "digilocker_records"
    __table_args__ = (
        CheckConstraint("doc_type IN ('aadhaar', 'pan', 'address_proof')", name="doc_type"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    persona_id: Mapped[str] = mapped_column(
        ForeignKey("personas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(30), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    issuer: Mapped[str] = mapped_column(String(120), nullable=False)


class CkycRecord(Base, TimestampMixin):
    """The CKYC mock: a masked registry number and a status."""

    __tablename__ = "ckyc_records"

    id: Mapped[uuid.UUID] = uuid_pk()
    persona_id: Mapped[str] = mapped_column(
        ForeignKey("personas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ckyc_number_masked: Mapped[str] = mapped_column(String(32), nullable=False)
    kyc_status: Mapped[str] = mapped_column(String(30), nullable=False)
    last_updated: Mapped[date] = mapped_column(Date, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class AaStatement(Base, TimestampMixin):
    """One month of Account Aggregator data. Six rows per persona feed the
    income average the suitability check uses (§9 OFFERS)."""

    __tablename__ = "aa_statements"

    id: Mapped[uuid.UUID] = uuid_pk()
    persona_id: Mapped[str] = mapped_column(
        ForeignKey("personas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fip_name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_masked: Mapped[str] = mapped_column(String(40), nullable=False)

    # First day of the month the row describes.
    month: Mapped[date] = mapped_column(Date, nullable=False)

    total_credits: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total_debits: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    avg_balance: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    bounce_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    existing_emi: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
