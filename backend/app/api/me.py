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

from app.db.models.user import User
from app.deps import CurrentAdmin, CurrentUser, DbDep
from app.errors import ApiError
from app.security.demo_auth import KNOWN_DEMO_IDENTITIES

router = APIRouter(tags=["me"])

Lang = Literal["mr-IN", "hi-IN", "en-IN"]
SessionKind = Literal["firebase", "demo"]


class PersonaSummary(BaseModel):
    """The linked synthetic customer.

    Only `id` is populated in phase 1 - `personas` is created in phase 2, which
    fills in the masked name, language and city. Kept as an object from the
    start so adding those fields does not change the shape clients decode.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    displayNameMasked: str | None = None
    language: Lang | None = None
    city: str | None = None


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
    def of(cls, user: User) -> MeResponse:
        persona = PersonaSummary(id=user.persona_id) if user.persona_id else None
        return cls(
            uid=user.firebase_uid,
            email=user.email,
            displayName=user.display_name,
            photoUrl=user.photo_url,
            preferredLanguage=user.preferred_language,  # type: ignore[arg-type]
            isAdmin=user.is_admin,
            session=user.session_kind,  # type: ignore[arg-type]
            persona=persona,
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


@router.get("/me", response_model=MeResponse)
def get_me(user: CurrentUser) -> MeResponse:
    """Return the signed-in user. The dependency upserts them on first call."""
    return MeResponse.of(user)


@router.patch("/me", response_model=MeResponse)
def patch_me(payload: MePatch, user: CurrentUser, db: DbDep) -> MeResponse:
    """Update the profile. Today that means `preferredLanguage` only."""
    if payload.preferredLanguage is not None:
        user.preferred_language = payload.preferredLanguage
        db.commit()
        db.refresh(user)
    return MeResponse.of(user)


@router.post("/me/persona", response_model=MeResponse)
def set_persona(payload: PersonaSwitch, admin: CurrentAdmin, db: DbDep) -> MeResponse:
    """Switch the linked persona (build plan section 8.2, admin only).

    Phase 2 validates the id against the `personas` table; until that exists,
    the check is against the known seed ids so a typo fails loudly now rather
    than producing a journey with no persona later.
    """
    persona_id = payload.personaId.strip().lower()
    if persona_id not in KNOWN_DEMO_IDENTITIES:
        raise ApiError("validation_error", f"Unknown persona '{payload.personaId}'.")

    admin.persona_id = persona_id
    db.commit()
    db.refresh(admin)
    return MeResponse.of(admin)
