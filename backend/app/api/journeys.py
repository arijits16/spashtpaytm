"""Journey routes (build plan §8.2, §9).

Every route here returns the same thing - a complete `TurnResponse` - so the
clients have exactly one rendering path whether they just started, just tapped,
or just came back from a killed app.

Four cross-cutting rules, applied to every route in the file:

* **Ownership returns 404.** Another user's journey is indistinguishable from
  one that does not exist (§13.2). A 403 would confirm it exists.
* **Idempotency through `clientTurnId`.** A repeated id replays the stored
  response rather than advancing the journey. Mobile networks retry; a loan
  application must not.
* **Rate limits per user**, from the §13.5 table.
* **One transaction per turn.** The state change, the audit rows and the
  idempotency record commit together.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.journey import Journey
from app.db.models.journey import TurnRequest as TurnRequestRow
from app.db.models.user import User
from app.deps import CurrentUser, DbDep, SettingsDep
from app.errors import ApiError, not_found
from app.journey import events, otp
from app.journey.engine import ConsentLocked, Engine, EngineResult
from app.journey.responses import TurnRequest, TurnResponse
from app.journey.states import DEFAULT_LANGUAGE, Lang, Status, Step
from app.security.ratelimit import client_identity, limiter

log = logging.getLogger(__name__)

router = APIRouter(tags=["journeys"], prefix="/journeys")

# Only one product exists. Modelled as an enum anyway so adding a second is a
# validation change rather than a new string appearing in the database.
Product = Literal["personal_loan"]


class StartJourneyRequest(BaseModel):
    """Body of `POST /api/journeys`."""

    model_config = ConfigDict(extra="forbid")

    product: Product = "personal_loan"

    # Sent by the app, which asks for the language on its own intro screen. When
    # present the engine skips the language card - asking twice is friction.
    language: Lang | None = None


class OtpSendResponse(BaseModel):
    """`POST /api/journeys/{id}/otp/send` (§8.2)."""

    model_config = ConfigDict(extra="forbid")

    sent: bool
    expiresInSec: int

    # Dev only, with `OTP_DEMO=true`. The app renders it as an obvious
    # fake-SMS banner so nobody mistakes it for a real message (§13.6).
    demoCode: str | None = None


class OtpVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Annotated[str, Field(pattern=r"^\d{6}$")]


# --- helpers -----------------------------------------------------------------


def _actor(user: User) -> str:
    """How the audit trail names this caller (§6 `audit_log.actor`)."""
    return "demo" if user.session_kind == "demo" else "customer"


def _owned(db: Session, journey_id: uuid.UUID, user: User) -> Journey:
    """Load a journey the caller owns, or raise 404.

    The ownership check is in the query, not after it: there is then no code
    path on which a journey belonging to someone else has been loaded into
    memory and could leak through a log line or an error message.
    """
    journey = db.scalar(select(Journey).where(Journey.id == journey_id, Journey.user_id == user.id))
    if journey is None:
        log.info(
            "journey not found or not owned",
            extra={"journey_id": str(journey_id), "user_id": str(user.id)},
        )
        raise not_found("Journey not found")
    return journey


def _active_journey(db: Session, user: User) -> Journey | None:
    """The caller's current journey, if any.

    `abandoned` counts as resumable: the rescue agent marks a journey abandoned
    while nobody is looking, and a customer who comes back should land where
    they left off rather than start again.
    """
    return db.scalar(
        select(Journey)
        .where(
            Journey.user_id == user.id,
            Journey.status.in_([Status.ACTIVE, Status.ABANDONED, Status.NEEDS_HUMAN]),
        )
        .order_by(Journey.last_activity_at.desc())
        .limit(1)
    )


def _finalise(
    db: Session,
    journey: Journey,
    result: EngineResult,
    settings: Settings,
    user: User,
) -> TurnResponse:
    """Everything that happens after the engine decides, before we answer.

    The receipt is appended here rather than inside the engine because it is a
    different concern - a signed, hash-chained ledger entry - and because the
    engine must stay a pure state machine that a reviewer can read end to end.
    Phase 6 fills this in; until then the step is reached and the card is empty.
    """
    response = result.response

    if result.needs_receipt:
        from app.trust.issue import issue_receipt

        card = issue_receipt(db, journey, settings, actor=_actor(user))
        if card is not None:
            response = response.model_copy(update={"card": card})
            journey.status = Status.COMPLETED
            response = response.model_copy(update={"status": "completed"})

    # The version bumps once per turn, after the engine has finished with the
    # row, so `expectedVersion` on the next request refers to what the client
    # has just been shown.
    journey.version += 1
    response = response.model_copy(update={"version": journey.version})

    db.flush()
    return response


def _store_turn(
    db: Session, journey: Journey, user: User, turn_id: uuid.UUID, response: TurnResponse
) -> None:
    """Record the response against `clientTurnId` so a retry replays it."""
    db.add(
        TurnRequestRow(
            client_turn_id=turn_id,
            journey_id=journey.id,
            user_id=user.id,
            response=response.model_dump(mode="json"),
        )
    )


def _replay(db: Session, turn_id: uuid.UUID, user: User) -> TurnResponse | None:
    """The stored response for a `clientTurnId`, if we have already served it.

    Scoped to the user as well as the id: a guessed UUID must not return
    somebody else's journey state.
    """
    row = db.scalar(
        select(TurnRequestRow).where(
            TurnRequestRow.client_turn_id == turn_id,
            TurnRequestRow.user_id == user.id,
        )
    )
    if row is None:
        return None
    return TurnResponse.model_validate(row.response)


def _check_version(journey: Journey, expected: int | None) -> None:
    """Optimistic lock (§8.3). Two racing taps become a 409, not a lost update."""
    if expected is not None and expected != journey.version:
        raise ApiError(
            "version_conflict",
            "This screen is out of date. Please reload the journey.",
        )


# --- routes ------------------------------------------------------------------


@router.post("", response_model=TurnResponse)
def start_journey(
    payload: StartJourneyRequest,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> TurnResponse:
    """Start a journey, or return the active one (§8.2).

    One active journey per user. Returning the existing one rather than refusing
    is what makes the app's "Try Spasht" button safe to tap twice.
    """
    limiter.enforce("turn", client_identity(request, str(user.id)))

    existing = _active_journey(db, user)
    if existing is not None:
        engine = Engine(db, existing, settings, actor=_actor(user))
        response = _finalise(db, existing, engine.resume(), settings, user)
        db.commit()
        return response

    journey = Journey(
        user_id=user.id,
        persona_id=user.persona_id,
        product=payload.product,
        language=payload.language or user.preferred_language or DEFAULT_LANGUAGE,
        step=str(Step.INTRO),
        status=Status.ACTIVE,
        context={"_meta": {"language_provided": payload.language is not None}},
        version=1,
    )
    db.add(journey)
    db.flush()

    engine = Engine(db, journey, settings, actor=_actor(user))
    response = _finalise(db, journey, engine.start(), settings, user)
    db.commit()
    return response


@router.get("/current", response_model=TurnResponse)
def current_journey(user: CurrentUser, db: DbDep, settings: SettingsDep) -> TurnResponse:
    """The active journey's latest screen, or 404 (§8.2).

    This is what makes "kill the app mid-journey and relaunch" work: the client
    asks where it was and renders the answer.
    """
    journey = _active_journey(db, user)
    if journey is None:
        raise not_found("No active journey")

    engine = Engine(db, journey, settings, actor=_actor(user))
    response = engine.resume().response
    db.commit()
    return response


@router.get("/{journey_id}", response_model=TurnResponse)
def get_journey(
    journey_id: uuid.UUID, user: CurrentUser, db: DbDep, settings: SettingsDep
) -> TurnResponse:
    """Re-render a journey the caller owns."""
    journey = _owned(db, journey_id, user)
    engine = Engine(db, journey, settings, actor=_actor(user))
    response = engine.resume().response
    db.commit()
    return response


@router.post("/{journey_id}/turn", response_model=TurnResponse)
def take_turn(
    journey_id: uuid.UUID,
    payload: TurnRequest,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> TurnResponse:
    """One customer turn: a tap or some text (§8.3).

    The idempotency check comes before the ownership load so a retry of a turn
    on a journey that has since completed still replays rather than 404ing.
    """
    limiter.enforce("turn", client_identity(request, str(user.id)))

    replayed = _replay(db, payload.clientTurnId, user)
    if replayed is not None:
        events.record(
            db,
            journey_id=journey_id,
            actor=_actor(user),
            event_type=events.TURN_REPLAYED,
            data={"clientTurnId": str(payload.clientTurnId)},
        )
        db.commit()
        return replayed

    journey = _owned(db, journey_id, user)
    _check_version(journey, payload.expectedVersion)

    if journey.status == Status.COMPLETED:
        raise ApiError("validation_error", "This journey is already complete.")

    engine = Engine(db, journey, settings, actor=_actor(user))
    try:
        result = engine.handle(payload.input)
    except ConsentLocked as exc:
        # 409, not 403: the request was legitimate and will succeed once the
        # teach-back passes, which is what the message says.
        db.commit()
        raise ApiError("consent_locked", str(exc)) from exc

    # PREFILL does the only non-database I/O in the journey, and the engine is
    # deliberately synchronous, so the adapters are driven from here.
    if engine.needs_prefill():
        engine.run_prefill_sync()
        result = engine.finish(user_message=result.user_message)

    response = _finalise(db, journey, result, settings, user)
    _store_turn(db, journey, user, payload.clientTurnId, response)
    db.commit()
    return response


@router.post("/{journey_id}/otp/send", response_model=OtpSendResponse)
def send_otp(
    journey_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> OtpSendResponse:
    """Issue a 6-digit code (§13.6).

    Refused with 409 unless the terms were actually accepted, which means the
    teach-back passed: the OTP confirms a consent, so it must not be obtainable
    before there is one to confirm.
    """
    limiter.enforce("otp_verify", client_identity(request, str(journey_id)))

    journey = _owned(db, journey_id, user)
    engine = Engine(db, journey, settings, actor=_actor(user))

    if not engine.context.terms_accepted:
        raise ApiError("consent_locked", "Accept the loan terms before requesting a code.")

    _challenge, demo_code = otp.issue(db, journey.id, settings)
    events.record(
        db,
        journey_id=journey.id,
        actor=_actor(user),
        event_type=events.OTP_SENT,
        step=journey.step,
        # Never the code, not even hashed - an audit row is read by an admin.
        data={"expiresInSec": otp.TTL_SECONDS},
    )
    db.commit()

    return OtpSendResponse(sent=True, expiresInSec=otp.TTL_SECONDS, demoCode=demo_code)


@router.post("/{journey_id}/otp/verify", response_model=TurnResponse)
def verify_otp(
    journey_id: uuid.UUID,
    payload: OtpVerifyRequest,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> TurnResponse:
    """Verify the code and, on success, issue the receipt (§8.2, §11).

    The consent gate is re-checked here as well as at `accept_terms`: OTP
    verification is the step that completes the loan, and §9 requires both
    entrances to the same room to be locked.
    """
    limiter.enforce("otp_verify", client_identity(request, str(journey_id)))

    journey = _owned(db, journey_id, user)
    engine = Engine(db, journey, settings, actor=_actor(user))

    if not engine.context.terms_accepted:
        raise ApiError("consent_locked", "Accept the loan terms first.")

    outcome = otp.verify(db, journey.id, payload.code, settings)

    if outcome != otp.OtpResult.OK:
        events.record(
            db,
            journey_id=journey.id,
            actor=_actor(user),
            event_type=events.OTP_FAILED,
            step=journey.step,
            data={"outcome": outcome},
        )
        db.commit()
        messages = {
            otp.OtpResult.WRONG: "That code is not right. Please try again.",
            otp.OtpResult.EXPIRED: "That code has expired. Please ask for a new one.",
            otp.OtpResult.LOCKED: "Too many attempts. Please ask for a new code.",
            otp.OtpResult.MISSING: "No code has been sent yet.",
        }
        raise ApiError("validation_error", messages[outcome])

    events.record(
        db,
        journey_id=journey.id,
        actor=_actor(user),
        event_type=events.OTP_VERIFIED,
        step=journey.step,
        data={},
    )

    # OTP success is what moves the journey to RECEIPT; `_finalise` then appends
    # the signed ledger entry and swaps in the receipt card.
    result = engine.complete()

    response = _finalise(db, journey, result, settings, user)
    journey.completed_at = journey.completed_at or journey.last_activity_at
    events.record(
        db,
        journey_id=journey.id,
        actor=_actor(user),
        event_type=events.JOURNEY_COMPLETED,
        step=journey.step,
        data={"offerId": journey.selected_offer_id},
    )
    db.commit()
    return response
