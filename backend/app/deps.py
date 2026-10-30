"""Shared FastAPI dependencies.

`current_user` is the single gate every protected route goes through. It accepts
either a Firebase ID token or - in dev, with the right key - the demo headers,
and always returns a persisted `User`.

Precedence is deliberate and mirrored in both clients: **a real bearer token
always wins**. If both are present the demo headers are ignored entirely, so the
UI can never show a demo badge while acting as the real user (decision D-016).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.firebase import TokenError, VerifiedToken, verify_id_token
from app.auth.users import upsert_user
from app.config import Settings, get_settings
from app.db.models.user import User
from app.db.session import get_db
from app.errors import forbidden, unauthorized
from app.security.demo_auth import DemoAuthError, demo_token, verify_demo_key
from app.security.ratelimit import client_identity, limiter

log = logging.getLogger(__name__)

# auto_error=False so a missing header becomes our own 401 in the standard
# envelope rather than FastAPI's, and so the demo headers can be tried instead.
bearer_scheme = HTTPBearer(auto_error=False)

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]

# One message for every authentication failure. Which condition failed - expired
# token, wrong audience, bad demo key, demo disabled - is logged, never
# returned: a precise message is a probing oracle (plan section 13.2).
_GENERIC_AUTH_FAILURE = "Not authenticated"


def current_user(
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    x_demo_user: Annotated[str | None, Header()] = None,
    x_demo_key: Annotated[str | None, Header()] = None,
) -> User:
    """Resolve the signed-in user, or raise 401."""
    token: VerifiedToken
    session_kind: str

    if credentials is not None and credentials.credentials:
        try:
            token = verify_id_token(credentials.credentials, settings)
        except TokenError as exc:
            log.info("token rejected", extra={"reason": str(exc)})
            raise unauthorized(_GENERIC_AUTH_FAILURE) from exc
        session_kind = "firebase"

    elif x_demo_user:
        # Rate-limited by IP *before* the key is checked, so the tunnel cannot
        # be used to guess the key at speed (plan section 13.5).
        limiter.enforce("demo_auth", client_identity(request))

        try:
            verify_demo_key(x_demo_key, settings)
        except DemoAuthError as exc:
            log.warning(
                "demo auth refused",
                extra={"reason": str(exc), "identity": x_demo_user},
            )
            raise unauthorized(_GENERIC_AUTH_FAILURE) from exc

        token = demo_token(x_demo_user)
        session_kind = "demo"

    else:
        raise unauthorized(_GENERIC_AUTH_FAILURE)

    user = upsert_user(db, token, settings, session_kind=session_kind)
    db.commit()
    db.refresh(user)
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def current_admin(user: CurrentUser) -> User:
    """Require an admin: a **verified** email on `DASHBOARD_ADMIN_EMAILS`.

    403, not 401: the caller is authenticated, just not permitted. Unlike the
    401s above, saying so is safe - they already proved who they are, and the
    message tells a teammate exactly what to fix.

    The verified-email requirement is the point of section 13.2: an address
    nobody has proved they own must not open the compliance dashboard, however
    it came to be on the allowlist.
    """
    if not user.is_admin:
        log.info(
            "admin route refused",
            extra={
                "user_id": str(user.id),
                "email_verified": user.email_verified,
                "session_kind": user.session_kind,
            },
        )
        raise forbidden("Admin access required")
    return user


CurrentAdmin = Annotated[User, Depends(current_admin)]
