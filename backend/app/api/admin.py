"""Admin and demo-control routes (build plan §8.2, §12).

Everything here is **admin + dev only**, checked twice: `CurrentAdmin` for who
is asking, and `APP_ENV=dev` for where. The reset truncates evidence tables
(§13.9), which is the one operation the append-only triggers exist to prevent -
so it must be impossible to reach anywhere but a laptop before a rehearsal.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.config import Settings
from app.db.models.journey import Journey
from app.db.models.persona import Persona
from app.db.models.user import User
from app.deps import CurrentAdmin, DbDep, SettingsDep
from app.errors import ApiError, forbidden
from app.events import bus as events_bus
from app.journey import events
from app.journey.states import Status, Step

log = logging.getLogger(__name__)

router = APIRouter(tags=["admin"], prefix="/admin")


class ResetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reset: bool
    counts: dict[str, int]


class AbandonedRequest(BaseModel):
    """Create a journey that looks abandoned, to demo the rescue agent."""

    model_config = ConfigDict(extra="forbid")

    personaId: str = "sunita"
    step: str = str(Step.OFFERS)

    # How long ago it was last touched. Must exceed `RESCUE_IDLE_SECONDS` for
    # the scheduler to pick it up, and the default comfortably does.
    idleSeconds: int = 180


class AbandonedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    journeyId: str
    step: str
    idleSeconds: int


def _require_dev(settings: Settings) -> None:
    """Refuse outside dev.

    Separate from the admin check on purpose: being an admin says who you are,
    and this says where you are. Both have to hold.
    """
    if not settings.is_dev:
        log.warning("demo control refused outside dev", extra={"env": settings.app_env})
        raise forbidden("Demo controls are only available in a dev environment.")


@router.post("/demo/reset", response_model=ResetResponse)
def reset_demo(admin: CurrentAdmin, db: DbDep, settings: SettingsDep) -> ResetResponse:
    """Wipe journey data, reset the ledger, re-seed the catalogue (§12).

    The same work as `make demo-reset`, exposed so the dashboard's demo
    controls can do it between rehearsals without a terminal.
    """
    _require_dev(settings)

    # Imported here rather than at module scope: it is a script, and the API
    # process has no reason to carry it unless this route is called.
    from sqlalchemy import text

    from app.db.models.trust import GENESIS_HASH
    from app.seed.run import run as reseed
    from scripts.demo_reset import JOURNEY_TABLES

    db.execute(text(f"TRUNCATE {', '.join(JOURNEY_TABLES)} CASCADE"))
    db.execute(
        text("UPDATE ledger_head SET last_seq = 0, last_hash = :h WHERE id = 1"),
        {"h": GENESIS_HASH},
    )
    db.execute(text("DELETE FROM users WHERE firebase_uid LIKE 'demo:%'"))
    db.commit()

    counts = reseed()

    log.info("demo data reset by an admin", extra={"user_id": str(admin.id)})
    events_bus.bus.publish(events_bus.DEMO_RESET, {"at": datetime.now(UTC).isoformat()})

    return ResetResponse(reset=True, counts=counts)


@router.post("/demo/abandoned-journey", response_model=AbandonedResponse)
def create_abandoned_journey(
    payload: AbandonedRequest, admin: CurrentAdmin, db: DbDep, settings: SettingsDep
) -> AbandonedResponse:
    """Create a journey stalled mid-way, so the rescue agent has something to
    find (§12, phase 10).

    It is attached to the demo customer rather than to the admin: the rescue
    call has to arrive on the phone, and the phone is signed in as `sunita`.
    """
    _require_dev(settings)

    persona = db.get(Persona, payload.personaId)
    if persona is None:
        raise ApiError("validation_error", f"Unknown persona '{payload.personaId}'.")

    try:
        step = Step(payload.step)
    except ValueError as exc:
        raise ApiError("validation_error", f"Unknown step '{payload.step}'.") from exc

    # The identity the iPhone's demo login resolves to, so the task it is
    # polling for is one it actually owns.
    customer = db.scalar(select(User).where(User.firebase_uid == f"demo:{persona.id}"))
    if customer is None:
        raise ApiError(
            "validation_error",
            f"No demo user for '{persona.id}' yet. Sign in on the phone once, then retry.",
        )

    idle_since = datetime.now(UTC) - timedelta(seconds=max(1, payload.idleSeconds))

    # A context far enough along that resuming lands somewhere meaningful:
    # an amount, both consents, and the prefilled details.
    context = {
        "amount": 50_000,
        "purpose": "machine",
        "consent_asked": True,
        "consent_digilocker": True,
        "consent_account_aggregator": True,
        "details_confirmed": True,
        "prefill": {
            "full_name": persona.full_name,
            "shop_address": persona.locality,
            "mobile": persona.mobile_masked,
            "monthly_income": 28_400,
            "existing_emi": 0,
            "sources": {"DigiLocker": "demo", "Account Aggregator": "demo"},
        },
    }

    journey = Journey(
        user_id=customer.id,
        persona_id=persona.id,
        product="personal_loan",
        language=persona.language,
        step=str(step),
        status=Status.ACTIVE,
        context=context,
        version=1,
        started_at=idle_since,
        last_activity_at=idle_since,
    )
    db.add(journey)
    db.flush()

    events.record(
        db,
        journey_id=journey.id,
        actor="admin",
        event_type=events.STEP_ENTERED,
        step=str(step),
        data={"createdBy": "demo control", "idleSeconds": payload.idleSeconds},
    )
    db.commit()

    log.info(
        "abandoned journey created for the rescue demo",
        extra={"journey_id": str(journey.id), "step": str(step)},
    )

    return AbandonedResponse(
        journeyId=str(journey.id), step=str(step), idleSeconds=payload.idleSeconds
    )


class PersonaRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    displayNameMasked: str
    language: str
    city: str
    occupation: str


@router.get("/personas", response_model=list[PersonaRow])
def list_personas(admin: CurrentAdmin, db: DbDep) -> list[PersonaRow]:
    """The personas the demo controls can switch between (§12)."""
    personas = db.scalars(select(Persona).order_by(Persona.id)).all()
    return [
        PersonaRow(
            id=persona.id,
            displayNameMasked=persona.display_name_masked,
            language=persona.language,
            city=persona.city,
            occupation=persona.occupation,
        )
        for persona in personas
    ]
