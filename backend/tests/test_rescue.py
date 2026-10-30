"""The rescue agent (build plan phase 10 acceptance criteria).

Two things are being asserted, and only the second one is about the feature
working at all.

**The call arrives and resumes the right step.** A journey left idle at OFFERS
produces a task, the phone's poll returns a call, and Accept answers with the
*same step* rather than a fresh journey.

**The call does not arrive when it must not.** Outside the contact window, on
DND, or without consent to callbacks, no call appears - and the task still
exists with `contact_window_ok = false`, so the dashboard can say why. That half
is the one worth having tests for: a rescue agent that rings at 2 a.m. is a
worse product than one that does not ring at all.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings, settings
from app.db.models.journey import Journey, RescueTask
from app.db.models.persona import Persona
from app.rescue import scheduler
from app.security.demo_auth import DEMO_ADMIN
from app.security.ratelimit import limiter


@pytest.fixture(autouse=True)
def _reset_limits() -> Iterator[None]:
    limiter.reset()
    yield
    limiter.reset()


# A window that always contains "now", so the route-level gate is not a clock
# race. The window rules get their own dedicated tests below.
OPEN_WINDOW = "00:00-23:59"


@pytest.fixture()
def open_window(client: TestClient) -> Iterator[Settings]:
    """Run the routes with the contact window wide open.

    The scheduler takes its settings as an argument, but the routes resolve
    theirs through FastAPI - so a test that only passed a copy to `tick` would
    still be judged by whatever hour the suite happens to run at.
    """
    config = settings.model_copy(update={"contact_window": OPEN_WINDOW})
    client.app.dependency_overrides[get_settings] = lambda: config
    try:
        yield config
    finally:
        client.app.dependency_overrides.pop(get_settings, None)


@pytest.fixture()
def demo_headers() -> dict[str, str]:
    return {"X-Demo-User": "sunita", "X-Demo-Key": settings.demo_auth_key}


@pytest.fixture()
def other_headers() -> dict[str, str]:
    """A second customer, used for the ownership checks."""
    return {"X-Demo-User": "ramesh", "X-Demo-Key": settings.demo_auth_key}


@pytest.fixture()
def admin_headers() -> dict[str, str]:
    return {"X-Demo-User": DEMO_ADMIN, "X-Demo-Key": settings.demo_auth_key}


def _persona(dnd: bool = False, consent: bool = True) -> Persona:
    """An unattached persona row, for the gate tests."""
    return Persona(id="x", full_name="X", dnd=dnd, consent_callbacks=consent)


def _stall(db: Session, journey_id: str, *, step: str = "OFFERS", seconds: int = 600) -> Journey:
    """Push a journey's last activity into the past, as if it were abandoned."""
    journey = db.get(Journey, journey_id)
    assert journey is not None
    journey.step = step
    journey.last_activity_at = datetime.now(UTC) - timedelta(seconds=seconds)
    db.commit()
    db.refresh(journey)
    return journey


def _abandoned(
    client: TestClient,
    admin_headers: dict[str, str],
    customer_headers: dict[str, str],
    *,
    persona: str = "sunita",
    step: str = "OFFERS",
) -> str:
    """Create a stalled journey through the dashboard's own demo control.

    The route tests go through `POST /admin/demo/abandoned-journey` rather than
    writing a step onto a fresh journey, because the engine renders from
    `step` + `context` - a journey parked at OFFERS with an empty context is
    not a customer who stopped at the offers, it is a corrupt row, and the
    engine rightly hands it to a human. This is also the exact path the phase
    10 acceptance criterion describes.
    """
    # The demo control attaches the journey to `demo:<persona>`, which exists
    # only once that phone has signed in.
    assert client.get("/api/me", headers=customer_headers).status_code == 200

    created = client.post(
        "/api/admin/demo/abandoned-journey",
        json={"personaId": persona, "step": step, "idleSeconds": 600},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    return created.json()["journeyId"]


def _start_journey(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/journeys", json={"product": "personal_loan", "language": "mr-IN"}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()["journeyId"]


# --- the contact-window rules ------------------------------------------------


def test_window_parsing_survives_a_malformed_value() -> None:
    """A bad `CONTACT_WINDOW` falls back rather than crashing or ringing at 2 a.m."""
    start, end = scheduler.parse_window("09:00-18:00")
    assert (start.hour, end.hour) == (9, 18)

    start, end = scheduler.parse_window("not a window")
    assert (start.hour, end.hour) == (9, 18)


def test_window_includes_and_excludes_the_right_times(
    settings_factory: Callable[..., Settings],
) -> None:
    config = settings_factory(contact_window="09:00-18:00")
    # 12:00 IST and 02:00 IST, expressed in UTC.
    noon = datetime(2026, 10, 30, 6, 30, tzinfo=UTC)
    night = datetime(2026, 10, 29, 20, 30, tzinfo=UTC)

    assert scheduler.within_window(config, noon) is True
    assert scheduler.within_window(config, night) is False


def test_window_can_wrap_midnight(settings_factory: Callable[..., Settings]) -> None:
    config = settings_factory(contact_window="22:00-06:00")
    night = datetime(2026, 10, 29, 20, 30, tzinfo=UTC)  # 02:00 IST
    assert scheduler.within_window(config, night) is True


@pytest.mark.parametrize(
    ("persona", "allowed"),
    [
        (_persona(), True),
        (_persona(dnd=True), False),
        (_persona(consent=False), False),
        (None, False),
    ],
)
def test_the_three_gates(
    persona: Persona | None, allowed: bool, settings_factory: Callable[..., Settings]
) -> None:
    """DND and a missing consent both block, independently of the clock."""
    config = settings_factory(contact_window="00:00-23:59")
    assert scheduler.may_contact(persona, config).allowed is allowed


def test_a_blocked_decision_explains_itself(settings_factory: Callable[..., Settings]) -> None:
    """The reason is stored on the task, so the dashboard can show the silence."""
    config = settings_factory(contact_window="00:00-23:59")
    assert "DND" in scheduler.may_contact(_persona(dnd=True), config).reason


# --- the scheduler -----------------------------------------------------------


def test_a_stalled_journey_raises_exactly_one_task(
    client: TestClient,
    db: Session,
    demo_headers: dict[str, str],
    open_window: Settings,
) -> None:
    journey_id = _start_journey(client, demo_headers)
    _stall(db, journey_id)

    assert len(scheduler.tick(open_window)) >= 1
    # A second tick must not ring the same application again.
    assert scheduler.tick(open_window) == []

    tasks = db.scalars(select(RescueTask).where(RescueTask.journey_id == journey_id)).all()
    assert len(tasks) == 1
    assert tasks[0].step == "OFFERS"
    assert tasks[0].contact_window_ok is True

    # Marked abandoned by us, never by a client.
    db.expire_all()
    journey = db.get(Journey, journey_id)
    assert journey is not None
    assert journey.status == "abandoned"


def test_a_fresh_journey_is_left_alone(
    client: TestClient,
    db: Session,
    demo_headers: dict[str, str],
    open_window: Settings,
) -> None:
    journey_id = _start_journey(client, demo_headers)
    config = open_window
    scheduler.tick(config)

    assert db.scalar(select(RescueTask).where(RescueTask.journey_id == journey_id)) is None


def test_an_unrescuable_step_is_left_alone(
    client: TestClient,
    db: Session,
    demo_headers: dict[str, str],
    open_window: Settings,
) -> None:
    """Nothing to resume *to* at INTRO, so no call is raised."""
    journey_id = _start_journey(client, demo_headers)
    _stall(db, journey_id, step="INTRO")

    config = open_window
    scheduler.tick(config)

    assert db.scalar(select(RescueTask).where(RescueTask.journey_id == journey_id)) is None


# --- the routes --------------------------------------------------------------


def test_pending_is_quiet_when_there_is_nothing(
    client: TestClient,
    demo_headers: dict[str, str],
    open_window: Settings,
) -> None:
    response = client.get("/api/rescue/pending", headers=demo_headers)
    assert response.status_code == 200
    assert response.json()["call"] is None
    assert response.json()["pollSeconds"] == 15


def test_pending_requires_auth(client: TestClient) -> None:
    assert client.get("/api/rescue/pending").status_code == 401


def test_the_call_arrives_and_accept_resumes_the_exact_step(
    client: TestClient,
    db: Session,
    demo_headers: dict[str, str],
    admin_headers: dict[str, str],
    open_window: Settings,
) -> None:
    """Phase 10's first acceptance criterion, end to end over HTTP."""
    journey_id = _abandoned(client, admin_headers, demo_headers)
    scheduler.tick(open_window)

    pending = client.get("/api/rescue/pending", headers=demo_headers)
    assert pending.status_code == 200, pending.text
    call = pending.json()["call"]
    assert call is not None
    assert call["journeyId"] == journey_id
    assert call["step"] == "OFFERS"
    assert call["line"]  # the rescue_call template, in the journey's language
    assert "{" not in call["line"]  # every placeholder filled
    assert call["language"] == "mr-IN"

    # Serving the call puts the task into 'ringing' for the dashboard.
    db.expire_all()
    task = db.get(RescueTask, call["taskId"])
    assert task is not None and task.status == "ringing"

    accepted = client.post(f"/api/rescue/{call['taskId']}/accept", headers=demo_headers)
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["journeyId"] == journey_id
    assert body["step"] == "OFFERS"
    # `abandoned` is internal and never reaches a client (§9).
    assert body["status"] == "active"

    db.expire_all()
    task = db.get(RescueTask, call["taskId"])
    journey = db.get(Journey, journey_id)
    assert task is not None and task.status == "resumed"
    assert journey is not None and journey.status == "active"
    assert journey.context.get("resumed_from_rescue") is True

    # Answered once: the phone must not be rung about it again.
    assert client.get("/api/rescue/pending", headers=demo_headers).json()["call"] is None


def test_declining_closes_the_task_for_good(
    client: TestClient,
    db: Session,
    demo_headers: dict[str, str],
    admin_headers: dict[str, str],
    open_window: Settings,
) -> None:
    _abandoned(client, admin_headers, demo_headers)
    scheduler.tick(open_window)

    call = client.get("/api/rescue/pending", headers=demo_headers).json()["call"]
    assert call is not None

    declined = client.post(f"/api/rescue/{call['taskId']}/decline", headers=demo_headers)
    assert declined.status_code == 200
    assert declined.json() == {"closed": True}

    assert client.get("/api/rescue/pending", headers=demo_headers).json()["call"] is None
    # And a closed task cannot be accepted afterwards.
    assert (
        client.post(f"/api/rescue/{call['taskId']}/accept", headers=demo_headers).status_code == 404
    )


def test_outside_the_contact_window_no_call_appears(
    client: TestClient, db: Session, demo_headers: dict[str, str]
) -> None:
    """Phase 10's second acceptance criterion.

    The task is still created - the dashboard has to be able to explain the
    silence - but the phone is told there is nothing.
    """
    journey_id = _start_journey(client, demo_headers)
    _stall(db, journey_id)

    # A window that cannot contain "now" in IST, whatever time the suite runs.
    now_ist = datetime.now(scheduler.IST)
    shut = (now_ist + timedelta(hours=3)).strftime("%H:%M")
    shut_end = (now_ist + timedelta(hours=4)).strftime("%H:%M")
    closed = settings.model_copy(update={"contact_window": f"{shut}-{shut_end}"})

    assert len(scheduler.tick(closed)) >= 1

    task = db.scalar(select(RescueTask).where(RescueTask.journey_id == journey_id))
    assert task is not None
    assert task.contact_window_ok is False
    assert "contact window" in task.reason

    assert client.get("/api/rescue/pending", headers=demo_headers).json()["call"] is None


def test_dnd_is_re_checked_at_poll_time(
    client: TestClient,
    db: Session,
    demo_headers: dict[str, str],
    admin_headers: dict[str, str],
    open_window: Settings,
) -> None:
    """A task raised while contactable stops ringing the moment DND is set.

    `contact_window_ok` is a record of what was true at creation. The gate is
    consulted again on every poll, so withdrawing consent takes effect now
    rather than at the next task.
    """
    _abandoned(client, admin_headers, demo_headers)
    scheduler.tick(open_window)

    persona = db.get(Persona, "sunita")
    assert persona is not None
    persona.dnd = True
    db.commit()
    try:
        assert client.get("/api/rescue/pending", headers=demo_headers).json()["call"] is None
    finally:
        persona.dnd = False
        db.commit()


def test_another_customers_task_is_a_404(
    client: TestClient,
    db: Session,
    demo_headers: dict[str, str],
    other_headers: dict[str, str],
    admin_headers: dict[str, str],
    open_window: Settings,
) -> None:
    """§13.2: another user's resource is indistinguishable from one that is not there."""
    _abandoned(client, admin_headers, demo_headers)
    scheduler.tick(open_window)

    call = client.get("/api/rescue/pending", headers=demo_headers).json()["call"]
    assert call is not None

    # The other customer sees neither the call nor the task.
    assert client.get("/api/rescue/pending", headers=other_headers).json()["call"] is None
    assert (
        client.post(f"/api/rescue/{call['taskId']}/accept", headers=other_headers).status_code
        == 404
    )
    assert (
        client.post(f"/api/rescue/{call['taskId']}/decline", headers=other_headers).status_code
        == 404
    )


def test_an_unknown_task_is_a_404(
    client: TestClient, demo_headers: dict[str, str], open_window: Settings
) -> None:
    unknown = "00000000-0000-4000-8000-000000000000"
    assert client.post(f"/api/rescue/{unknown}/accept", headers=demo_headers).status_code == 404
