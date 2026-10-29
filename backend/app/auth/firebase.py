"""Firebase ID token verification (build plan section 13).

Two verification paths, tried in order:

1. `firebase_admin.auth.verify_id_token` - the normal path. Initialised with
   `FIREBASE_PROJECT_ID`; a service-account JSON is optional.
2. `google.oauth2.id_token.verify_firebase_token` - the fallback for machines
   with no ambient Google credentials, which is the common hackathon-laptop case.

Both check signature, issuer, audience and expiry against Google's public keys.
The result is a small `VerifiedToken`, never the raw claims, so nothing
sensitive travels further into the app.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import firebase_admin
import google.auth.transport.requests
from firebase_admin import auth as fb_auth
from firebase_admin import credentials
from google.auth.exceptions import GoogleAuthError
from google.oauth2 import id_token as google_id_token

from app.config import Settings

log = logging.getLogger(__name__)

_init_lock = threading.Lock()
_app: firebase_admin.App | None = None
_request_session = google.auth.transport.requests.Request()


class TokenError(Exception):
    """The token is missing, malformed, expired or not ours."""


@dataclass(frozen=True, slots=True)
class VerifiedToken:
    """The only claims Spasht needs. Deliberately minimal."""

    uid: str
    email: str | None
    name: str | None
    picture: str | None
    email_verified: bool


def _get_firebase_app(settings: Settings) -> firebase_admin.App | None:
    """Initialise `firebase_admin` once. Returns None when unavailable.

    A None result is not fatal: the caller falls back to `google-auth`.
    """
    global _app
    if _app is not None:
        return _app

    with _init_lock:
        if _app is not None:
            return _app
        if not settings.firebase_project_id:
            return None
        try:
            cred_path = settings.google_application_credentials
            cred = (
                credentials.Certificate(str(Path(cred_path).expanduser()))
                if cred_path and Path(cred_path).expanduser().is_file()
                else None
            )
            _app = firebase_admin.initialize_app(
                cred, {"projectId": settings.firebase_project_id}, name="spasht"
            )
            log.info(
                "firebase-admin initialised",
                extra={"with_service_account": cred is not None},
            )
        except Exception as exc:  # noqa: BLE001 - never block startup on auth wiring
            log.warning(
                "firebase-admin unavailable, using google-auth fallback",
                extra={"error_type": type(exc).__name__},
            )
            _app = None
    return _app


def _claims_to_token(claims: dict[str, Any]) -> VerifiedToken:
    """Map provider claims onto our minimal shape."""
    uid = claims.get("uid") or claims.get("sub") or claims.get("user_id")
    if not uid:
        raise TokenError("token carries no subject")
    return VerifiedToken(
        uid=str(uid),
        email=claims.get("email"),
        name=claims.get("name"),
        picture=claims.get("picture"),
        email_verified=bool(claims.get("email_verified", False)),
    )


def verify_id_token(token: str, settings: Settings) -> VerifiedToken:
    """Verify a Firebase ID token and return the claims we care about.

    @param token     The raw JWT from `Authorization: Bearer <token>`.
    @param settings  Needs `firebase_project_id` as the expected audience.
    @throws TokenError on any invalid, expired or foreign token.
    """
    if not token:
        raise TokenError("no token supplied")
    if not settings.firebase_project_id:
        raise TokenError("FIREBASE_PROJECT_ID is not configured")

    app = _get_firebase_app(settings)
    if app is not None:
        try:
            return _claims_to_token(fb_auth.verify_id_token(token, app=app))
        except fb_auth.InvalidIdTokenError as exc:
            raise TokenError("invalid id token") from exc
        except fb_auth.ExpiredIdTokenError as exc:
            raise TokenError("expired id token") from exc
        except Exception as exc:  # noqa: BLE001 - fall through to google-auth
            log.info(
                "firebase-admin verification failed, trying google-auth",
                extra={"error_type": type(exc).__name__},
            )

    # Fallback: verifies signature, issuer, audience and expiry with no
    # ambient Google credentials required.
    try:
        claims = google_id_token.verify_firebase_token(
            token, _request_session, audience=settings.firebase_project_id
        )
    except (GoogleAuthError, ValueError) as exc:
        raise TokenError("token verification failed") from exc

    if not claims:
        raise TokenError("token verification returned no claims")
    return _claims_to_token(claims)


def reset_for_tests() -> None:
    """Drop the cached app so tests can re-init with different settings."""
    global _app
    with _init_lock:
        if _app is not None:
            # Teardown is best effort: a half-deleted app still gets replaced.
            with contextlib.suppress(Exception):
                firebase_admin.delete_app(_app)
        _app = None
