"""The Rescue Agent (build plan §9, §12, phase 10).

Someone opens a loan application, gets as far as the offers, and stops. Maybe a
customer walked into the shop. The application sits there, and in most products
that is the end of it.

This finds those journeys and offers to continue. Every 15 seconds it looks for
journeys idle at a resumable step and creates a `rescue_tasks` row; the phone
polls, shows an incoming-call screen, and Accept resumes **at the exact step**.

**The rules about when not to call are the important part.** An agent that can
ring someone is an agent that can harass them, so three conditions are checked
before a call is offered, and a task that fails them is still *created* with
`contact_window_ok = false` so the dashboard can explain the silence:

1. inside `CONTACT_WINDOW` (09:00-18:00 IST by default);
2. the persona consented to callbacks;
3. the persona is not on DND.

A journey gets **one** task, ever. Nobody is rung twice about the same
application.

In production the call would be placed by a telephony provider (Exotel,
Twilio). Here it is an in-app screen, which is noted in `docs/DECISIONS.md`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.journey import Journey, RescueTask
from app.db.models.persona import Persona
from app.db.session import SessionLocal
from app.events.bus import publish_rescue_created
from app.journey import events
from app.journey.states import RESCUABLE_STEPS, Status

log = logging.getLogger(__name__)

# §12: the loop runs every 15 s.
TICK_SECONDS = 15

# How many stalled journeys one tick will look at. A cap so a backlog cannot
# turn a single tick into a long transaction; the rest are picked up next tick.
BATCH_LIMIT = 50

# IST. The contact window is a local-time rule - "nobody rings at 2 a.m." means
# 2 a.m. where the customer is, not UTC.
IST = timezone(timedelta(hours=5, minutes=30), "IST")


@dataclass(frozen=True, slots=True)
class ContactDecision:
    """Whether a call may be placed, and why not if it may not.

    The reason is stored on the task and shown on the dashboard, because an
    agent that cannot explain its own silence is one nobody will trust to stay
    silent when it should.
    """

    allowed: bool
    reason: str


def parse_window(raw: str) -> tuple[time, time]:
    """Parse `CONTACT_WINDOW` ("09:00-18:00").

    A malformed value falls back to 09:00-18:00 rather than raising. The
    alternative - a crash on startup, or a window of "always" - is worse: one
    takes the backend down, the other rings people at night.
    """
    try:
        start_text, end_text = raw.split("-", 1)
        start = time.fromisoformat(start_text.strip())
        end = time.fromisoformat(end_text.strip())
        return start, end
    except (ValueError, AttributeError):
        log.warning("CONTACT_WINDOW is malformed; using 09:00-18:00", extra={"raw": raw})
        return time(9, 0), time(18, 0)


def within_window(settings: Settings, now: datetime | None = None) -> bool:
    """Whether the local time is inside the contact window."""
    start, end = parse_window(settings.contact_window)
    local = (now or datetime.now(UTC)).astimezone(IST).time()
    if start <= end:
        return start <= local <= end
    # A window that wraps midnight, e.g. 22:00-06:00.
    return local >= start or local <= end


def may_contact(
    persona: Persona | None, settings: Settings, now: datetime | None = None
) -> ContactDecision:
    """The three gates, in the order that respects the customer most.

    DND is checked first and independently of everything else: it is the
    customer's own standing instruction, and it should not matter what time it
    is or what they consented to on some earlier screen.
    """
    if persona is None:
        return ContactDecision(False, "no persona linked to this journey")

    if persona.dnd:
        return ContactDecision(False, "the customer is on DND")

    if not persona.consent_callbacks:
        return ContactDecision(False, "the customer did not consent to callbacks")

    if not within_window(settings, now):
        start, end = parse_window(settings.contact_window)
        return ContactDecision(
            False,
            f"outside the contact window ({start:%H:%M}-{end:%H:%M} IST)",
        )

    return ContactDecision(True, "inside the contact window")


def find_stalled(db: Session, settings: Settings) -> list[Journey]:
    """Journeys idle long enough, at a step worth resuming to.

    Only `RESCUABLE_STEPS` (§9): earlier than PREFILL there is nothing to
    resume *to*, and past OTP the customer has either finished or a human is
    already calling them.

    Journeys that already have a task are excluded **in the query**, not after
    it. With the filter applied afterwards, the batch limit filled up with the
    oldest already-handled journeys and a newly stalled one was never reached -
    so the demo control created a journey and the phone never rang.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=max(10, settings.rescue_idle_seconds))

    already_raised = select(RescueTask.id).where(RescueTask.journey_id == Journey.id).exists()

    candidates = db.scalars(
        select(Journey)
        .where(
            Journey.status.in_([Status.ACTIVE, Status.ABANDONED]),
            Journey.last_activity_at < cutoff,
            Journey.step.in_([str(step) for step in RESCUABLE_STEPS]),
            ~already_raised,
        )
        .order_by(Journey.last_activity_at)
        .limit(BATCH_LIMIT)
    ).all()

    return list(candidates)


def existing_task(db: Session, journey_id) -> RescueTask | None:
    """Any task already raised for this journey.

    One per journey, ever. Checked against *every* status, not just pending: a
    task that was closed or already resumed must not produce a second call.
    """
    return db.scalar(select(RescueTask).where(RescueTask.journey_id == journey_id))


def create_task(db: Session, journey: Journey, settings: Settings) -> RescueTask | None:
    """Raise a task for a stalled journey, or None if one already exists."""
    if existing_task(db, journey.id) is not None:
        return None

    persona = db.get(Persona, journey.persona_id) if journey.persona_id else None
    decision = may_contact(persona, settings)

    idle_seconds = int((datetime.now(UTC) - journey.last_activity_at).total_seconds())

    task = RescueTask(
        journey_id=journey.id,
        # 'human' when the journey was handed off, 'stuck' when it just stopped.
        kind="human" if journey.status == Status.NEEDS_HUMAN else "stuck",
        reason=f"idle {idle_seconds}s at {journey.step} - {decision.reason}",
        step=journey.step,
        status="pending",
        contact_window_ok=decision.allowed,
    )
    db.add(task)

    # Marked abandoned by *us*, never by a client: a customer who closed the app
    # has not decided anything, and the wire never carries this status (§9).
    if journey.status == Status.ACTIVE:
        journey.status = Status.ABANDONED

    events.record(
        db,
        journey_id=journey.id,
        actor="agent",
        event_type=events.RESCUE_CREATED,
        step=journey.step,
        data={
            "idleSeconds": idle_seconds,
            "contactWindowOk": decision.allowed,
            "reason": decision.reason,
        },
    )
    db.flush()

    # Deliberately *not* published here. `tick` runs on a worker thread, and the
    # bus hands events to `asyncio.Queue`s owned by the main loop - a
    # `put_nowait` from another thread is not thread-safe and can leave a
    # connected dashboard un-woken. `run_forever` publishes what the tick
    # created, from the loop.
    log.info(
        "rescue task created",
        extra={
            "journey_id": str(journey.id),
            "step": journey.step,
            "contact_window_ok": decision.allowed,
        },
    )
    return task


def tick(settings: Settings) -> list[dict[str, object]]:
    """One pass. Returns the dashboard payload for each task created.

    Its own session, committed per tick: the scheduler is a background loop and
    must not hold a transaction open across sleeps, where it would sit on row
    locks that a customer's turn needs.

    The payloads are returned rather than published because this runs on a
    worker thread; see `create_task` and `run_forever`.
    """
    created: list[dict[str, object]] = []
    with SessionLocal() as db:
        try:
            for journey in find_stalled(db, settings):
                task = create_task(db, journey, settings)
                if task is not None:
                    created.append(
                        {
                            "task_id": task.id,
                            "journey_id": journey.id,
                            "step": journey.step,
                            "reason": task.reason,
                        }
                    )
            db.commit()
        except Exception:  # a background loop must not die
            log.exception("rescue tick failed; rolling back and trying again next tick")
            db.rollback()
            return []
    return created


async def run_forever(settings: Settings) -> None:
    """The loop, started from the app's lifespan.

    Every failure is caught and logged. A background task that dies takes the
    rescue feature with it silently, which is exactly the kind of thing nobody
    notices until the demo.
    """
    log.info(
        "rescue agent started",
        extra={
            "tick_seconds": TICK_SECONDS,
            "idle_seconds": settings.rescue_idle_seconds,
            "window": settings.contact_window,
        },
    )

    while True:
        try:
            await asyncio.sleep(TICK_SECONDS)
            # `to_thread` because `tick` is synchronous SQLAlchemy; running it
            # inline would block the event loop for the length of the query.
            created = await asyncio.to_thread(tick, settings)

            # Published from the loop, after the thread is done: the dashboard's
            # live feed then sees the task within its two-second budget (§12).
            for payload in created:
                publish_rescue_created(**payload)  # type: ignore[arg-type]

            if created:
                log.info("rescue agent raised %d task(s)", len(created))
        except asyncio.CancelledError:
            log.info("rescue agent stopped")
            raise
        except Exception:  # keep the loop alive
            log.exception("rescue agent tick raised; continuing")
