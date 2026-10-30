"""Upserting the signed-in user.

Called on every authenticated request, so it must be cheap and idempotent.
Profile fields are refreshed from the token (the user may have changed their
Google photo), and `is_admin` is recomputed from the allowlist every time -
admin rights are never client-supplied and never sticky (decision D-014).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.firebase import VerifiedToken
from app.config import Settings
from app.db.models.user import User
from app.security.demo_auth import demo_persona_id

log = logging.getLogger(__name__)

# Phase 2 links real personas; until then every new customer gets the golden one.
DEFAULT_PERSONA_ID = "sunita"


def is_admin_email(email: str | None, email_verified: bool, settings: Settings) -> bool:
    """True when a **verified** email is on `DASHBOARD_ADMIN_EMAILS`.

    Both halves matter (plan section 13.2). Anyone can put an address into a
    Firebase profile; only Google can mark it verified. Without that check, the
    allowlist would admit whoever claimed one of its addresses.
    """
    if not email or not email_verified:
        return False
    return email.strip().lower() in settings.admin_email_list


def _persona_for(token: VerifiedToken) -> str | None:
    """Which persona a new user is linked to.

    Demo identities map to their own persona (and `demo-admin` to none, since a
    dashboard operator has no journey). Real users get the golden persona.
    """
    if token.uid.startswith("demo:"):
        return demo_persona_id(token.uid.removeprefix("demo:"))
    return DEFAULT_PERSONA_ID


def upsert_user(
    db: Session,
    token: VerifiedToken,
    settings: Settings,
    *,
    session_kind: str = "firebase",
) -> User:
    """Find or create the `users` row for a verified token, refreshing profile data.

    @param db            Open session; the caller commits.
    @param token         Already-verified claims. This function never verifies.
    @param settings      Supplies the admin allowlist.
    @param session_kind  'firebase' or 'demo' - how this request authenticated.
    @returns The persisted `User`.
    """
    user = db.scalar(select(User).where(User.firebase_uid == token.uid))
    admin = is_admin_email(token.email, token.email_verified, settings)
    now = datetime.now(UTC)

    if user is None:
        user = User(
            firebase_uid=token.uid,
            email=token.email,
            email_verified=token.email_verified,
            display_name=token.name,
            photo_url=token.picture,
            persona_id=_persona_for(token),
            is_admin=admin,
            session_kind=session_kind,
            last_login_at=now,
        )
        db.add(user)
        db.flush()
        log.info(
            "user created",
            extra={"user_id": str(user.id), "is_admin": admin, "session_kind": session_kind},
        )
        return user

    # Refresh the profile; leave preferred_language alone, the user owns it.
    user.email = token.email
    user.email_verified = token.email_verified
    user.display_name = token.name
    user.photo_url = token.picture
    user.is_admin = admin
    user.session_kind = session_kind
    user.last_login_at = now
    if user.persona_id is None and session_kind != "demo":
        user.persona_id = DEFAULT_PERSONA_ID
    db.flush()
    return user
