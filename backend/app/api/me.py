"""`GET /api/me` and `PATCH /api/me` (build plan section 8.1)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.db.models.user import User
from app.deps import CurrentUser, DbDep

router = APIRouter(tags=["me"])

Lang = Literal["mr-IN", "hi-IN", "en-IN"]


class MeResponse(BaseModel):
    """The signed-in user's profile.

    Field names are camelCase to match the frontend; `persona` is filled in
    properly in phase 2 when the personas table exists.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str | None
    displayName: str | None
    photoUrl: str | None
    preferredLanguage: Lang
    personaId: str | None
    isAdmin: bool

    @classmethod
    def of(cls, user: User) -> MeResponse:
        return cls(
            id=str(user.id),
            email=user.email,
            displayName=user.display_name,
            photoUrl=user.photo_url,
            preferredLanguage=user.preferred_language,  # type: ignore[arg-type]
            personaId=user.persona_id,
            isAdmin=user.is_admin,
        )


class MePatch(BaseModel):
    """Only the language is user-editable. `is_admin` is never client-settable."""

    preferredLanguage: Annotated[Lang | None, Field(default=None)]


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
