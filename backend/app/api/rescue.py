"""Rescue routes (build plan §8.2, §12, phase 10).

Three routes, all owner-scoped, that turn a `rescue_tasks` row into something
the phone can show:

* `GET /api/rescue/pending` - the one call waiting for *this* customer, or
  nothing. Polled every 15 s while the app is in the foreground.
* `POST /api/rescue/{taskId}/accept` - the customer picked up: the journey
  becomes active again and the answer is a full `TurnResponse` for **the exact
  step they stopped on**.
* `POST /api/rescue/{taskId}/decline` - they did not want the call. The task
  closes so the phone is never rung twice about the same application.

Two rules worth being explicit about.

**The contact window is re-checked at poll time, not only at creation.** The
scheduler stamps `contact_window_ok` so the dashboard can explain itself, but a
task raised at 17:59 must not start ringing at 18:05. `may_contact` is the
single gate, and it is consulted here again on every poll.

**Ownership returns 404** (§13.2). A task id that belongs to someone else is
indistinguishable from one that does not exist.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.sarvam_client import demo_mode_active
from app.ai.tts import cache_key, cached_url, is_cached, synthesise
from app.config import Settings
from app.db.models.journey import Journey, RescueTask
from app.db.models.persona import Persona
from app.db.models.user import User
from app.deps import CurrentUser, DbDep, SettingsDep
from app.errors import not_found
from app.events.bus import publish_journey_updated
from app.journey import events
from app.journey.engine import Engine
from app.journey.responses import TurnResponse
from app.journey.states import Lang, Status
from app.journey.templates import honorific, render
from app.rescue.scheduler import may_contact
from app.security.ratelimit import client_identity, limiter
from app.voice.turns import attach_audio

log = logging.getLogger(__name__)

router = APIRouter(tags=["rescue"], prefix="/rescue")

# What the incoming-call screen shows as the caller. A concept demo must never
# look like it is actually Paytm calling, which is why the subtitle says so.
CALLER_NAME = "Spasht · Paytm Loans"
CALLER_SUBTITLE = "Concept demo · simulated call"

# The app's poll interval, sent rather than hard-coded in the client so the
# cadence can change without an app release.
POLL_SECONDS = 15

# Statuses a task can be ringing on. A `resumed` or `closed` task is finished
# with: it must never reappear on the phone.
OPEN_STATUSES = ("pending", "ringing")


class RescueCall(BaseModel):
    """One incoming call, as the iPhone renders it (§5.11)."""

    model_config = ConfigDict(extra="forbid")

    taskId: str
    journeyId: str
    kind: str
    step: str
    language: Lang
    callerName: str = CALLER_NAME
    subtitle: str = CALLER_SUBTITLE

    # The `rescue_call` template line (§8.6), in the journey's language, and the
    # cached mp3 for it. `audioUrl` may be null - the caption is always on
    # screen, so silence degrades to reading rather than to a broken call.
    line: str
    audioUrl: str | None = None

    createdAt: str


class PendingResponse(BaseModel):
    """`GET /api/rescue/pending`."""

    model_config = ConfigDict(extra="forbid")

    call: RescueCall | None = None
    pollSeconds: int = POLL_SECONDS


class DeclineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    closed: bool


# --- helpers -----------------------------------------------------------------


def _actor(user: User) -> str:
    """How the audit trail names this caller (§6 `audit_log.actor`)."""
    return "demo" if user.session_kind == "demo" else "customer"


def _owned_task(db: Session, task_id: uuid.UUID, user: User) -> tuple[RescueTask, Journey]:
    """Load a task whose journey the caller owns, or raise 404.

    The ownership predicate is in the query, joined through `journeys`: there is
    then no code path on which another customer's task has been loaded into
    memory and could leak through a log line.
    """
    row = db.execute(
        select(RescueTask, Journey)
        .join(Journey, Journey.id == RescueTask.journey_id)
        .where(RescueTask.id == task_id, Journey.user_id == user.id)
    ).first()

    if row is None:
        log.info(
            "rescue task not found or not owned",
            extra={"task_id": str(task_id), "user_id": str(user.id)},
        )
        raise not_found("Rescue task not found")

    return row[0], row[1]


def _spoken_line(db: Session, journey: Journey) -> str:
    """The `rescue_call` line, named for whoever is being called."""
    persona = db.get(Persona, journey.persona_id) if journey.persona_id else None
    language: Lang = journey.language  # type: ignore[assignment]
    name = honorific(persona.name_local or {}, language) if persona else ""
    return render("rescue_call", language, name_honorific=name)


async def _audio_for(line: str, language: Lang, settings: Settings) -> str | None:
    """The cached mp3 for the call line, synthesising it only if we must.

    `make tts-cache` pre-generates this line per persona, so the demo path is a
    cache hit and costs nothing. In demo mode a miss stays a miss - a dead
    network must still produce a call screen with a caption on it (§10.6).
    """
    if not line:
        return None

    key = cache_key(line, language, settings)
    if is_cached(key):
        return cached_url(key)

    if demo_mode_active(settings):
        log.info("demo mode: the rescue line has no cached audio")
        return None

    try:
        return await synthesise(line, language, settings)
    except Exception:  # noqa: BLE001 - a silent call still works
        log.warning("tts failed for the rescue line")
        return None


# --- routes ------------------------------------------------------------------


@router.get("/pending", response_model=PendingResponse)
async def pending_rescue(
    request: Request, user: CurrentUser, db: DbDep, settings: SettingsDep
) -> PendingResponse:
    """The call waiting for this customer, if one may be placed right now.

    Answers `{call: null}` rather than 404 when there is nothing: the app polls
    this every 15 s, and an error status for the normal case would turn a quiet
    afternoon into a screenful of logged failures.
    """
    limiter.enforce("turn", client_identity(request, str(user.id)))

    row = db.execute(
        select(RescueTask, Journey)
        .join(Journey, Journey.id == RescueTask.journey_id)
        .where(
            Journey.user_id == user.id,
            RescueTask.status.in_(OPEN_STATUSES),
            RescueTask.contact_window_ok.is_(True),
        )
        .order_by(RescueTask.created_at)
        .limit(1)
    ).first()

    if row is None:
        return PendingResponse(call=None)

    task, journey = row

    # Re-checked here, not trusted from creation time: a task raised inside the
    # window must stop ringing when the window closes, and DND or a withdrawn
    # consent takes effect immediately rather than at the next task.
    persona = db.get(Persona, journey.persona_id) if journey.persona_id else None
    decision = may_contact(persona, settings)
    if not decision.allowed:
        log.info(
            "rescue call withheld",
            extra={"task_id": str(task.id), "reason": decision.reason},
        )
        return PendingResponse(call=None)

    line = _spoken_line(db, journey)
    audio_url = await _audio_for(line, journey.language, settings)  # type: ignore[arg-type]

    # 'ringing' is set on the first poll that actually serves the call, so the
    # dashboard distinguishes "raised" from "the phone is ringing now".
    if task.status == "pending":
        task.status = "ringing"
        events.record(
            db,
            journey_id=journey.id,
            actor="agent",
            event_type=events.RESCUE_CREATED,
            step=journey.step,
            data={"ringing": True, "taskId": str(task.id)},
        )
    db.commit()

    return PendingResponse(
        call=RescueCall(
            taskId=str(task.id),
            journeyId=str(journey.id),
            kind=task.kind,
            step=task.step,
            language=journey.language,  # type: ignore[arg-type]
            line=line,
            audioUrl=audio_url,
            createdAt=task.created_at.isoformat(),
        )
    )


@router.post("/{task_id}/accept", response_model=TurnResponse)
async def accept_rescue(
    task_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> TurnResponse:
    """The customer picked up: resume the journey at the exact step.

    No transition happens. The card is rebuilt from `step` + `context` by the
    same `resume()` the relaunch path uses, which is what makes "continue where
    you stopped" literal rather than approximate.
    """
    limiter.enforce("turn", client_identity(request, str(user.id)))

    task, journey = _owned_task(db, task_id, user)

    # Idempotent: a double tap, or a retry after a dropped response, resumes
    # again instead of failing. Only a task somebody declined stays closed.
    if task.status == "closed":
        raise not_found("Rescue task not found")

    task.status = "resumed"

    # The customer is back, so the journey is active again - `abandoned` was our
    # guess about them, and they have just disproved it.
    if journey.status == Status.ABANDONED:
        journey.status = Status.ACTIVE

    engine = Engine(db, journey, settings, actor=_actor(user))
    engine.context.resumed_from_rescue = True
    result = engine.resume()
    response = result.response

    events.record(
        db,
        journey_id=journey.id,
        actor=_actor(user),
        event_type=events.RESCUE_ACCEPTED,
        step=journey.step,
        data={"taskId": str(task.id), "kind": task.kind},
    )

    # The live table and the rescue page both move on this.
    publish_journey_updated(
        journey.id,
        step=journey.step,
        status=journey.status,
        persona_id=journey.persona_id,
        language=journey.language,
    )

    await attach_audio(response, settings)
    db.commit()

    log.info(
        "rescue accepted",
        extra={"task_id": str(task.id), "journey_id": str(journey.id), "step": journey.step},
    )
    return response


@router.post("/{task_id}/decline", response_model=DeclineResponse)
def decline_rescue(
    task_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> DeclineResponse:
    """The customer declined. The task closes and is never offered again.

    Declining is not a client-side gesture: a task left open would ring again on
    the next poll fifteen seconds later, which is precisely the harassment the
    contact-window rules exist to prevent.
    """
    limiter.enforce("turn", client_identity(request, str(user.id)))

    task, journey = _owned_task(db, task_id, user)

    if task.status != "resumed":
        task.status = "closed"
        events.record(
            db,
            journey_id=journey.id,
            actor=_actor(user),
            event_type=events.RESCUE_CREATED,
            step=journey.step,
            data={"declined": True, "taskId": str(task.id)},
        )
    db.commit()
    return DeclineResponse(closed=True)
