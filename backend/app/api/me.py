"""`GET /api/me` and `PATCH /api/me` (build plan section 8.2).

Shape:

    {uid, email, displayName, photoUrl, preferredLanguage, isAdmin, session, persona}

Both the iPhone app and the website decode exactly this, and
`contracts/fixtures/me.json` is the copy they are tested against.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.db.models.persona import Persona
from app.db.models.user import User
from app.deps import CurrentAdmin, CurrentUser, DbDep
from app.errors import ApiError

router = APIRouter(tags=["me"])

Lang = Literal["mr-IN", "hi-IN", "en-IN"]
SessionKind = Literal["firebase", "demo"]


class PersonaSummary(BaseModel):
    """The linked synthetic customer (phase 2 fills every field from `personas`).

    Only masked values appear here. The persona's full name exists in the
    database because the assistant needs it to build the spoken honorific
    ("सुनीता ताई"), but nothing that reaches a client ever carries it.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    displayNameMasked: str | None = None
    language: Lang | None = None
    city: str | None = None
    occupation: str | None = None
    mobileMasked: str | None = None

    @classmethod
    def of(cls, persona: Persona) -> PersonaSummary:
        return cls(
            id=persona.id,
            displayNameMasked=persona.display_name_masked,
            language=persona.language,  # type: ignore[arg-type]
            city=persona.city,
            occupation=persona.occupation,
            mobileMasked=persona.mobile_masked,
        )


class MeResponse(BaseModel):
    """The signed-in user's profile. camelCase to match the clients (section 8.1)."""

    model_config = ConfigDict(extra="forbid")

    uid: str
    email: str | None
    displayName: str | None
    photoUrl: str | None
    preferredLanguage: Lang
    isAdmin: bool

    # 'firebase' | 'demo'. The UI shows a demo badge from this rather than from
    # its own state, so the badge cannot disagree with the server.
    session: SessionKind

    # Null for `demo-admin`, who operates the dashboard and has no journey.
    persona: PersonaSummary | None

    @classmethod
    def of(cls, user: User, persona: Persona | None = None) -> MeResponse:
        # A linked persona id with no row behind it would be a seeding bug; the
        # id alone is still returned so the demo keeps working and the gap is
        # visible rather than silent.
        summary = (
            PersonaSummary.of(persona)
            if persona is not None
            else (PersonaSummary(id=user.persona_id) if user.persona_id else None)
        )
        return cls(
            uid=user.firebase_uid,
            email=user.email,
            displayName=user.display_name,
            photoUrl=user.photo_url,
            preferredLanguage=user.preferred_language,  # type: ignore[arg-type]
            isAdmin=user.is_admin,
            session=user.session_kind,  # type: ignore[arg-type]
            persona=summary,
        )


class MePatch(BaseModel):
    """Only the language is user-editable.

    `extra="forbid"` so a client sending `isAdmin` gets a clear 422 rather than
    having it silently ignored - the latter looks like it worked.
    """

    model_config = ConfigDict(extra="forbid")

    preferredLanguage: Annotated[Lang | None, Field(default=None)]


class PersonaSwitch(BaseModel):
    """Body of `POST /api/me/persona` (admin only)."""

    model_config = ConfigDict(extra="forbid")

    personaId: str


def _persona_of(db: DbDep, user: User) -> Persona | None:
    """Load the linked persona row, if there is one."""
    if not user.persona_id:
        return None
    return db.get(Persona, user.persona_id)


@router.get("/me", response_model=MeResponse)
def get_me(user: CurrentUser, db: DbDep) -> MeResponse:
    """Return the signed-in user. The dependency upserts them on first call."""
    return MeResponse.of(user, _persona_of(db, user))


@router.patch("/me", response_model=MeResponse)
def patch_me(payload: MePatch, user: CurrentUser, db: DbDep) -> MeResponse:
    """Update the profile. Today that means `preferredLanguage` only."""
    if payload.preferredLanguage is not None:
        user.preferred_language = payload.preferredLanguage
        db.commit()
        db.refresh(user)
    return MeResponse.of(user, _persona_of(db, user))


@router.post("/me/persona", response_model=MeResponse)
def set_persona(payload: PersonaSwitch, admin: CurrentAdmin, db: DbDep) -> MeResponse:
    """Switch the linked persona (build plan section 8.2, admin only).

    Validated against the `personas` table rather than a hard-coded list, so a
    persona added to the seed file is immediately selectable and a typo fails
    here instead of producing a journey with no persona several steps later.

    422 rather than 404: the caller named something that is not a persona, which
    is a bad request, not a missing resource of theirs.
    """
    persona_id = payload.personaId.strip().lower()
    persona = db.scalar(select(Persona).where(Persona.id == persona_id))
    if persona is None:
        raise ApiError("validation_error", f"Unknown persona '{payload.personaId}'.")

    admin.persona_id = persona.id
    db.commit()
    db.refresh(admin)
    return MeResponse.of(admin, persona)
