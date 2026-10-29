"""Upserting the signed-in user.

Called on every authenticated request, so it must be cheap and idempotent.
Profile fields are refreshed from the token (the user may have changed their
Google photo), and `is_admin` is recomputed from the allowlist every time -
admin rights are never client-supplied and never sticky.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.firebase import VerifiedToken
from app.config import Settings
from app.db.models.user import User

log = logging.getLogger(__name__)

# Phase 2 links real personas; until then every new user gets the golden one.
DEFAULT_PERSONA_ID = "sunita"


def is_admin_email(email: str | None, settings: Settings) -> bool:
    """True when the email is on `DASHBOARD_ADMIN_EMAILS` (case-insensitive)."""
    if not email:
        return False
    return email.strip().lower() in settings.admin_email_list


def upsert_user(db: Session, token: VerifiedToken, settings: Settings) -> User:
    """Find or create the `users` row for a verified token, refreshing profile data.

    @param db        Open session; the caller commits.
    @param token     Already-verified claims. This function never verifies.
    @param settings  Supplies the admin allowlist.
    @returns The persisted `User`.
    """
    user = db.scalar(select(User).where(User.firebase_uid == token.uid))
    admin = is_admin_email(token.email, settings)

    if user is None:
        user = User(
            firebase_uid=token.uid,
            email=token.email,
            display_name=token.name,
            photo_url=token.picture,
            persona_id=DEFAULT_PERSONA_ID,
            is_admin=admin,
        )
        db.add(user)
        db.flush()
        log.info("user created", extra={"user_id": str(user.id), "is_admin": admin})
        return user

    # Refresh the profile; leave preferred_language alone, the user owns it.
    user.email = token.email
    user.display_name = token.name
    user.photo_url = token.picture
    user.is_admin = admin
    if user.persona_id is None:
        user.persona_id = DEFAULT_PERSONA_ID
    db.flush()
    return user
