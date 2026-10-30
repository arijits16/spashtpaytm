"""Shared FastAPI dependencies.

`current_user` is the single gate every protected route goes through. It accepts
either a Firebase ID token or - in dev with `DEMO_AUTH=true` - the `X-Demo-User`
header, and always returns a persisted `User`.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.demo import demo_token
from app.auth.firebase import TokenError, VerifiedToken, verify_id_token
from app.auth.users import upsert_user
from app.config import Settings, get_settings
from app.db.models.user import User
from app.db.session import get_db
from app.errors import forbidden, unauthorized

log = logging.getLogger(__name__)

# auto_error=False so a missing header becomes our own 401 with a clear message
# rather than FastAPI's default, and so the demo header can be tried instead.
bearer_scheme = HTTPBearer(auto_error=False)

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]


def current_user(
    db: DbDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    x_demo_user: Annotated[str | None, Header()] = None,
) -> User:
    """Resolve the signed-in user, or raise 401.

    A real bearer token always wins; the demo header is only consulted when no
    token was supplied and the environment explicitly allows it.
    """
    token: VerifiedToken

    if credentials is not None and credentials.credentials:
        try:
            token = verify_id_token(credentials.credentials, settings)
        except TokenError as exc:
            # The reason is logged, not returned: it is a probing oracle.
            log.info("token rejected", extra={"reason": str(exc)})
            raise unauthorized("Invalid or expired credentials") from exc

    elif x_demo_user and settings.demo_auth_allowed:
        token = demo_token(x_demo_user)

    elif x_demo_user:
        # The header was sent but the environment forbids it - say so plainly.
        raise unauthorized("Demo auth is disabled")

    else:
        raise unauthorized("Not authenticated")

    user = upsert_user(db, token, settings)
    db.commit()
    db.refresh(user)
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def current_admin(user: CurrentUser) -> User:
    """Require an admin (the `DASHBOARD_ADMIN_EMAILS` allowlist).

    403, not 401: the caller is authenticated, just not permitted.
    """
    if not user.is_admin:
        raise forbidden("Admin access required")
    return user


CurrentAdmin = Annotated[User, Depends(current_admin)]
