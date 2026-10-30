"""The journey itself and its append-only evidence trail (plan §6, §9).

Four of these tables - `consents`, `teachback_attempts`, `audit_log` and
`receipts` (in `trust.py`) - are **append-only**, enforced by a PL/pgSQL
`BEFORE UPDATE OR DELETE` trigger. That is what lets a receipt stand as
evidence: nobody, including this application, can quietly rewrite what the
customer was told or agreed to.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, uuid_pk

# The engine's state machine (§8.4 `Step`).
STEPS: tuple[str, ...] = (
    "INTRO",
    "ASK_NEED",
    "CONSENT_DATA",
    "MANUAL_FORM",
    "PREFILL",
    "CONFIRM_DETAILS",
    "OFFERS",
    "EXPLAIN_KFS",
    "TEACHBACK",
    "TERMS_CONSENT",
    "OTP",
    "RECEIPT",
    "DONE",
    "HUMAN_HANDOFF",
)

CONSENT_PURPOSES: tuple[str, ...] = (
    "fetch_digilocker",
    "fetch_account_aggregator",
    "loan_terms",
    "insurance_addon",
    "callback",
)


class Journey(Base):
    """One customer's loan conversation.

    `step` + `context` is the whole state: the engine is a pure function of them,
    so a backend restart mid-demo loses nothing. `version` is an optimistic lock
    that stops two taps racing.
    """

    __tablename__ = "journeys"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'abandoned', 'needs_human')", name="status"
        ),
        # The two queries that matter: "my active journey" (resume) and
        # "journeys idle long enough to rescue" (phase 10).
        Index("ix_journeys_user_status", "user_id", "status"),
        Index("ix_journeys_status_activity", "status", "last_activity_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    persona_id: Mapped[str | None] = mapped_column(ForeignKey("personas.id"), nullable=True)

    product: Mapped[str] = mapped_column(String(40), nullable=False, server_default="personal_loan")
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="mr-IN")
    step: Mapped[str] = mapped_column(String(30), nullable=False, server_default="INTRO")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")

    # Everything the engine remembers: requested amount, prefilled rows, quiz
    # progress, consent grants. Shapes live in `journey/context.py`.
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    selected_offer_id: Mapped[str | None] = mapped_column(
        ForeignKey("loan_offers.id"), nullable=True
    )
    kfs_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("kfs_documents.id"), nullable=True
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # Deliberately *not* `onupdate`: the rescue agent needs the last time the
    # customer did something, which is not the last time any column changed.
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TurnRequest(Base):
    """Idempotency record: `clientTurnId` -> the response we already sent.

    A retry after a flaky tunnel must not advance the journey twice, so the
    client generates the id and we replay the stored response verbatim. Rows are
    disposable after 24 h (§6).
    """

    __tablename__ = "turn_requests"
    __table_args__ = (Index("ix_turn_requests_created", "created_at"),)

    client_turn_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    journey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ConversationTurn(Base):
    """One line of the conversation, encrypted at rest.

    The text is AES-256-GCM (§11.2) because a transcript is the most personal
    thing in the database; only an admin sees it decrypted, on the dashboard.
    The latency columns are what prove the <4 s voice budget (§10.4).
    """

    __tablename__ = "conversation_turns"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role"),
        Index("ix_conversation_turns_journey", "journey_id", "turn_no"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    journey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False
    )
    turn_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)

    text_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    language: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)

    stt_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tts_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TeachbackAttempt(Base):
    """Append-only: every answer, right or wrong, with how it was graded.

    `attempt_no == 1 and is_correct` is the first-attempt pass rate the
    dashboard charts per question (§12).
    """

    __tablename__ = "teachback_attempts"
    __table_args__ = (
        CheckConstraint("answer_type IN ('option', 'voice', 'text')", name="answer_type"),
        CheckConstraint("grader IN ('rule', 'llm')", name="grader"),
        Index("ix_teachback_attempts_journey", "journey_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    journey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("teachback_questions.id"), nullable=False, index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_type: Mapped[str] = mapped_column(String(10), nullable=False)
    answer_value: Mapped[str] = mapped_column(String(500), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    grader: Mapped[str] = mapped_column(String(10), nullable=False, server_default="rule")
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Consent(Base):
    """Append-only consent evidence.

    `default_value` is stored alongside `granted` on purpose: proving a toggle
    *started* off is what shows the customer chose it rather than failed to
    notice it. Withdrawing a consent inserts a new row; nothing is updated.
    """

    __tablename__ = "consents"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('fetch_digilocker', 'fetch_account_aggregator', 'loan_terms', "
            "'insurance_addon', 'callback')",
            name="purpose",
        ),
        CheckConstraint("method IN ('tap', 'voice', 'tap+otp')", name="method"),
        Index("ix_consents_journey", "journey_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    journey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    default_value: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    method: Mapped[str] = mapped_column(String(10), nullable=False, server_default="tap")

    # What was on screen when they agreed: the exact terms text, the step, the
    # request id. A consent with no context is not evidence.
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OtpChallenge(Base, TimestampMixin):
    """A 6-digit code, stored only as an HMAC (§13.6).

    Not append-only: `attempts` and `locked` have to change. The code itself is
    never stored, never logged and never spoken.
    """

    __tablename__ = "otp_challenges"

    id: Mapped[uuid.UUID] = uuid_pk()
    journey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    """Append-only event trail. Every engine transition writes one row (§9)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint("actor IN ('customer', 'demo', 'system', 'agent', 'admin')", name="actor"),
        Index("ix_audit_log_journey", "journey_id", "created_at"),
        Index("ix_audit_log_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    journey_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=True
    )
    actor: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    step: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Never a transcript and never a secret: the redaction rules of §13.8 apply
    # here exactly as they do to logs.
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RescueTask(Base, TimestampMixin):
    """A pending call-back for an abandoned journey (phase 10).

    `contact_window_ok` is recorded at creation so the dashboard can explain why
    a task exists but no call was placed.
    """

    __tablename__ = "rescue_tasks"
    __table_args__ = (
        CheckConstraint("kind IN ('stuck', 'human')", name="kind"),
        CheckConstraint("status IN ('pending', 'ringing', 'resumed', 'closed')", name="status"),
        Index("ix_rescue_tasks_status", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    journey_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False, server_default="stuck")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    step: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    contact_window_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
