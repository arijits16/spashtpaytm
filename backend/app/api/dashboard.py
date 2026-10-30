"""The lender and compliance dashboard (build plan §12, phase 9).

Admin-only, and the admin check is server-side on every route (§13.2): hiding a
page on the website is cosmetic, and the dashboard shows every journey in the
system rather than only the caller's.

**What the KPIs are for.** This is not an engagement dashboard. Each number
answers a question a compliance officer would actually ask:

* *first-attempt pass rate per question* - if 40% get the late fee wrong on
  their first try, the KFS wording is the problem, not the customer (§12);
* *insurance opt-in %* - a high number means somebody is bundling, which is the
  practice this product argues against;
* *AI numbers blocked by the guard* - a guard that never fires is either
  unnecessary or broken, and an operator should be able to tell which;
* *human handoffs* - people the product could not help, which is the honest
  measure of its limits.

Transcripts are decrypted here and nowhere else (§11.2), for an admin, in the
journey detail drawer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import case, func, select

from app.db.models.journey import (
    AuditLog,
    Consent,
    ConversationTurn,
    Journey,
    RescueTask,
    TeachbackAttempt,
)
from app.db.models.persona import Persona
from app.db.models.trust import Receipt
from app.deps import CurrentAdmin, DbDep, SettingsDep
from app.errors import not_found
from app.events.bus import bus
from app.journey.context import JourneyContext
from app.journey.states import Step
from app.trust.crypto_box import decrypt

log = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"], prefix="/dashboard")

# The funnel's order. The engine's own step list, minus the branches that are
# not progress - a funnel with a handoff in the middle of it reads as though
# handoffs were a stage everyone passes through.
FUNNEL_STEPS: tuple[str, ...] = (
    str(Step.INTRO),
    str(Step.ASK_NEED),
    str(Step.CONSENT_DATA),
    str(Step.PREFILL),
    str(Step.CONFIRM_DETAILS),
    str(Step.OFFERS),
    str(Step.EXPLAIN_KFS),
    str(Step.TEACHBACK),
    str(Step.TERMS_CONSENT),
    str(Step.OTP),
    str(Step.DONE),
)

MAX_ROWS = 100


class Kpis(BaseModel):
    """The §12 overview numbers."""

    model_config = ConfigDict(extra="forbid")

    startedToday: int
    completedToday: int
    completionPct: float
    medianSecondsToComplete: int | None

    teachbackFirstAttemptPct: float
    reexplanations: int
    humanHandoffs: int

    # Low is good: it means nothing is being bundled (§12).
    insuranceOptInPct: float

    # A guard that never fires is worth a question (§10.5).
    guardBlocked: int

    languageSplit: dict[str, int]
    receiptsTotal: int
    liveJourneys: int


class FunnelStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: str
    label: str
    reached: int


class QuestionStat(BaseModel):
    """Per-question first-attempt pass rate - the §12 chart that matters."""

    model_config = ConfigDict(extra="forbid")

    questionId: str
    attempts: int
    firstAttemptPassed: int
    firstAttemptPct: float
    eventuallyPassed: int


class OverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kpis: Kpis
    funnel: list[FunnelStep]
    questions: list[QuestionStat]
    generatedAt: str


class JourneyRow(BaseModel):
    """One row of the live table. Masked names only."""

    model_config = ConfigDict(extra="forbid")

    journeyId: str
    personaId: str | None
    personaName: str | None
    language: str
    step: str
    status: str
    amount: int | None
    selectedOffer: str | None
    durationSeconds: int
    lastActivitySeconds: int
    receiptNo: str | None
    isLive: bool


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: str
    actor: str
    eventType: str
    step: str | None
    data: dict[str, Any]


class TranscriptLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turnNo: int
    role: str
    text: str
    source: str
    at: str
    sttMs: int | None
    llmMs: int | None


class AttemptRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questionId: str
    attemptNo: int
    answerType: str
    isCorrect: bool
    grader: str
    at: str


class ConsentRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str
    granted: bool
    defaultValue: bool
    method: str
    at: str


class JourneyDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    journey: JourneyRow
    timeline: list[TimelineEvent]
    transcript: list[TranscriptLine]
    attempts: list[AttemptRow]
    consents: list[ConsentRow]
    suitability: dict[str, Any]
    receiptNo: str | None


class ReceiptRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receiptNo: str
    seq: int
    shortHash: str
    lender: str
    language: str
    createdAt: str


class RescueRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    taskId: str
    journeyId: str
    kind: str
    reason: str
    step: str
    status: str
    contactWindowOk: bool
    createdAt: str


# --- helpers ----------------------------------------------------------------


def _today_start() -> datetime:
    """Midnight UTC. Displayed as IST on the website (§6)."""
    return datetime.combine(datetime.now(UTC).date(), datetime.min.time(), tzinfo=UTC)


def _seconds_since(moment: datetime | None) -> int:
    if moment is None:
        return 0
    return max(0, int((datetime.now(UTC) - moment).total_seconds()))


def _journey_row(journey: Journey, persona_name: str | None, receipt_no: str | None) -> JourneyRow:
    context = JourneyContext.of(journey.context)
    completed = journey.completed_at or datetime.now(UTC)
    return JourneyRow(
        journeyId=str(journey.id),
        personaId=journey.persona_id,
        personaName=persona_name,
        language=journey.language,
        step=journey.step,
        status=journey.status,
        amount=context.amount,
        selectedOffer=journey.selected_offer_id,
        durationSeconds=max(0, int((completed - journey.started_at).total_seconds())),
        lastActivitySeconds=_seconds_since(journey.last_activity_at),
        receiptNo=receipt_no,
        # Pulsing dot on the website: active and touched in the last minute.
        isLive=journey.status == "active" and _seconds_since(journey.last_activity_at) < 60,
    )


# --- routes -----------------------------------------------------------------


@router.get("/overview", response_model=OverviewResponse)
def overview(admin: CurrentAdmin, db: DbDep) -> OverviewResponse:
    """The KPIs, the funnel and the per-question pass rates (§12)."""
    since = _today_start()

    started = (
        db.scalar(select(func.count()).select_from(Journey).where(Journey.started_at >= since)) or 0
    )
    completed = (
        db.scalar(
            select(func.count())
            .select_from(Journey)
            .where(Journey.started_at >= since, Journey.status == "completed")
        )
        or 0
    )
    handoffs = (
        db.scalar(
            select(func.count())
            .select_from(Journey)
            .where(Journey.started_at >= since, Journey.status == "needs_human")
        )
        or 0
    )

    # Median in SQL rather than in Python: `percentile_cont` is exact and does
    # not need every row pulled into the process.
    median_seconds = db.scalar(
        select(
            func.percentile_cont(0.5).within_group(
                func.extract("epoch", Journey.completed_at - Journey.started_at)
            )
        ).where(Journey.completed_at.is_not(None), Journey.started_at >= since)
    )

    # First-attempt pass rate across every question.
    first_attempts = db.execute(
        select(
            func.count().label("total"),
            func.sum(case((TeachbackAttempt.is_correct, 1), else_=0)).label("passed"),
        ).where(TeachbackAttempt.attempt_no == 1)
    ).one()
    first_total = first_attempts.total or 0
    first_passed = first_attempts.passed or 0

    reexplanations = (
        db.scalar(
            select(func.count())
            .select_from(TeachbackAttempt)
            .where(TeachbackAttempt.attempt_no > 1)
        )
        or 0
    )

    # Insurance opt-in, over the journeys that were actually asked.
    insurance = db.execute(
        select(
            func.count().label("asked"),
            func.sum(case((Consent.granted, 1), else_=0)).label("taken"),
        ).where(Consent.purpose == "insurance_addon")
    ).one()
    asked = insurance.asked or 0
    taken = insurance.taken or 0

    guard_blocked = (
        db.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.event_type == "guard.blocked")
        )
        or 0
    )

    language_rows = db.execute(
        select(Journey.language, func.count())
        .where(Journey.started_at >= since)
        .group_by(Journey.language)
    ).all()

    receipts_total = db.scalar(select(func.count()).select_from(Receipt)) or 0
    live = (
        db.scalar(select(func.count()).select_from(Journey).where(Journey.status == "active")) or 0
    )

    kpis = Kpis(
        startedToday=started,
        completedToday=completed,
        completionPct=round(100 * completed / started, 1) if started else 0.0,
        medianSecondsToComplete=int(median_seconds) if median_seconds else None,
        teachbackFirstAttemptPct=(
            round(100 * first_passed / first_total, 1) if first_total else 0.0
        ),
        reexplanations=reexplanations,
        humanHandoffs=handoffs,
        insuranceOptInPct=round(100 * taken / asked, 1) if asked else 0.0,
        guardBlocked=guard_blocked,
        languageSplit=dict(language_rows),
        receiptsTotal=receipts_total,
        liveJourneys=live,
    )

    # The funnel counts journeys that *reached* a step, from the audit trail
    # rather than from the current step - a completed journey passed through
    # OFFERS even though it is no longer there.
    reached_rows = db.execute(
        select(AuditLog.step, func.count(func.distinct(AuditLog.journey_id)))
        .where(AuditLog.event_type == "step.entered", AuditLog.created_at >= since)
        .group_by(AuditLog.step)
    ).all()
    reached = dict(reached_rows)

    labels = {
        str(Step.INTRO): "Start",
        str(Step.ASK_NEED): "Amount",
        str(Step.CONSENT_DATA): "Consent",
        str(Step.PREFILL): "Prefill",
        str(Step.CONFIRM_DETAILS): "Confirm",
        str(Step.OFFERS): "Offers",
        str(Step.EXPLAIN_KFS): "Explain",
        str(Step.TEACHBACK): "Teach-back",
        str(Step.TERMS_CONSENT): "Agree",
        str(Step.OTP): "Confirm OTP",
        str(Step.DONE): "Done",
    }
    funnel = [
        FunnelStep(step=step, label=labels.get(step, step), reached=reached.get(step, 0))
        for step in FUNNEL_STEPS
    ]

    question_rows = db.execute(
        select(
            TeachbackAttempt.question_id,
            func.count().label("attempts"),
            func.sum(
                case(
                    (
                        (TeachbackAttempt.attempt_no == 1) & TeachbackAttempt.is_correct,
                        1,
                    ),
                    else_=0,
                )
            ).label("first_passed"),
            func.count(func.distinct(TeachbackAttempt.journey_id)).label("journeys"),
            func.sum(case((TeachbackAttempt.is_correct, 1), else_=0)).label("passed"),
        ).group_by(TeachbackAttempt.question_id)
    ).all()

    questions = [
        QuestionStat(
            questionId=row.question_id,
            attempts=row.attempts,
            firstAttemptPassed=row.first_passed or 0,
            firstAttemptPct=(
                round(100 * (row.first_passed or 0) / row.journeys, 1) if row.journeys else 0.0
            ),
            eventuallyPassed=row.passed or 0,
        )
        for row in question_rows
    ]

    return OverviewResponse(
        kpis=kpis,
        funnel=funnel,
        questions=questions,
        generatedAt=datetime.now(UTC).isoformat(),
    )


@router.get("/journeys", response_model=list[JourneyRow])
def list_journeys(admin: CurrentAdmin, db: DbDep, limit: int = 50) -> list[JourneyRow]:
    """The live table (§12), newest activity first."""
    rows = db.execute(
        select(Journey, Persona.display_name_masked, Receipt.receipt_no)
        .outerjoin(Persona, Persona.id == Journey.persona_id)
        .outerjoin(Receipt, Receipt.journey_id == Journey.id)
        .order_by(Journey.last_activity_at.desc())
        .limit(min(max(1, limit), MAX_ROWS))
    ).all()

    return [
        _journey_row(journey, persona_name, receipt_no)
        for journey, persona_name, receipt_no in rows
    ]


@router.get("/journeys/{journey_id}", response_model=JourneyDetailResponse)
def journey_detail(
    journey_id: uuid.UUID, admin: CurrentAdmin, db: DbDep, settings: SettingsDep
) -> JourneyDetailResponse:
    """The detail drawer: timeline, decrypted transcript, attempts, consents.

    This is the only place a transcript is decrypted (§11.2), and only for an
    admin. A line whose key has rotated shows as unreadable rather than failing
    the whole page.
    """
    row = db.execute(
        select(Journey, Persona.display_name_masked, Receipt.receipt_no)
        .outerjoin(Persona, Persona.id == Journey.persona_id)
        .outerjoin(Receipt, Receipt.journey_id == Journey.id)
        .where(Journey.id == journey_id)
    ).one_or_none()

    if row is None:
        raise not_found("Journey not found")

    journey, persona_name, receipt_no = row
    context = JourneyContext.of(journey.context)

    timeline = [
        TimelineEvent(
            at=entry.created_at.isoformat(),
            actor=entry.actor,
            eventType=entry.event_type,
            step=entry.step,
            data=entry.data or {},
        )
        for entry in db.scalars(
            select(AuditLog)
            .where(AuditLog.journey_id == journey_id)
            .order_by(AuditLog.created_at, AuditLog.id)
        ).all()
    ]

    transcript = []
    for turn in db.scalars(
        select(ConversationTurn)
        .where(ConversationTurn.journey_id == journey_id)
        .order_by(ConversationTurn.turn_no)
    ).all():
        text = decrypt(turn.text_enc, turn.nonce, settings, aad=str(journey_id))
        transcript.append(
            TranscriptLine(
                turnNo=turn.turn_no,
                role=turn.role,
                text=text if text is not None else "[could not be decrypted]",
                source=turn.source,
                at=turn.created_at.isoformat(),
                sttMs=turn.stt_ms,
                llmMs=turn.llm_ms,
            )
        )

    attempts = [
        AttemptRow(
            questionId=attempt.question_id,
            attemptNo=attempt.attempt_no,
            answerType=attempt.answer_type,
            isCorrect=attempt.is_correct,
            grader=attempt.grader,
            at=attempt.created_at.isoformat(),
        )
        for attempt in db.scalars(
            select(TeachbackAttempt)
            .where(TeachbackAttempt.journey_id == journey_id)
            .order_by(TeachbackAttempt.created_at, TeachbackAttempt.id)
        ).all()
    ]

    consents = [
        ConsentRow(
            purpose=consent.purpose,
            granted=consent.granted,
            defaultValue=consent.default_value,
            method=consent.method,
            at=consent.created_at.isoformat(),
        )
        for consent in db.scalars(
            select(Consent)
            .where(Consent.journey_id == journey_id)
            .order_by(Consent.created_at, Consent.id)
        ).all()
    ]

    return JourneyDetailResponse(
        journey=_journey_row(journey, persona_name, receipt_no),
        timeline=timeline,
        transcript=transcript,
        attempts=attempts,
        consents=consents,
        suitability={
            "foir": context.foir,
            "decision": "suitable" if context.suitable else "not_suitable",
            "reasons": context.suitability_reasons,
            "incomeVerified": not context.prefill.self_declared,
            "monthlyIncome": context.prefill.monthly_income,
        },
        receiptNo=receipt_no,
    )


@router.get("/receipts", response_model=list[ReceiptRow])
def list_receipts(admin: CurrentAdmin, db: DbDep, limit: int = 50) -> list[ReceiptRow]:
    """The receipts table (§12)."""
    receipts = db.scalars(
        select(Receipt).order_by(Receipt.seq.desc()).limit(min(max(1, limit), MAX_ROWS))
    ).all()

    return [
        ReceiptRow(
            receiptNo=receipt.receipt_no,
            seq=receipt.seq,
            shortHash=receipt.hash[:16],
            lender=(receipt.payload or {}).get("lender", ""),
            language=(receipt.payload or {}).get("language", ""),
            createdAt=receipt.created_at.isoformat(),
        )
        for receipt in receipts
    ]


@router.get("/rescue-tasks", response_model=list[RescueRow])
def list_rescue_tasks(admin: CurrentAdmin, db: DbDep) -> list[RescueRow]:
    """The rescue tasks page (phase 10)."""
    tasks = db.scalars(
        select(RescueTask).order_by(RescueTask.created_at.desc()).limit(MAX_ROWS)
    ).all()

    return [
        RescueRow(
            taskId=str(task.id),
            journeyId=str(task.journey_id),
            kind=task.kind,
            reason=task.reason,
            step=task.step,
            status=task.status,
            contactWindowOk=task.contact_window_ok,
            createdAt=task.created_at.isoformat(),
        )
        for task in tasks
    ]


@router.get("/stream")
async def stream(admin: CurrentAdmin) -> StreamingResponse:
    """SSE: `journey.updated`, `receipt.created`, `rescue.created`, `guard.blocked`.

    The token travels in the `Authorization` header, because the website uses
    fetch-event-source rather than the browser's own `EventSource` - which
    cannot set headers and would have forced the token into the query string,
    where it would end up in logs.
    """
    return StreamingResponse(
        bus.subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            # Tells nginx not to buffer the stream, which would defeat it.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
