"""Hardened dev-only demo authentication (build plan section 13.2).

`X-Demo-User: sunita` + `X-Demo-Key: <DEMO_AUTH_KEY>` stands in for a Firebase
login so the demo survives a dead venue network. It is a real way into the API,
and during a demo the API is reachable from the internet through the ngrok
tunnel - so it is gated on **four** conditions, every one of which must hold:

1. `DEMO_AUTH=true`
2. `APP_ENV=dev`
3. `DEMO_AUTH_KEY` is non-empty
4. the caller's `X-Demo-Key` equals it, compared in constant time

Conditions 1-3 are the environment's decision and 4 is the caller's. The key
check exists because the first three are all things *we* control: without it,
anyone who found the tunnel URL would be one header away from a session.

iOS Release builds carry no key at all (`Release.xcconfig` blanks it), so the
demo path cannot be used from a shipped app even if the server allowed it.
"""

from __future__ import annotations

import hmac
import logging

from app.auth.firebase import VerifiedToken
from app.config import Settings

log = logging.getLogger(__name__)

DEMO_USER_HEADER = "X-Demo-User"
DEMO_KEY_HEADER = "X-Demo-Key"

# The two identities from section 13.2. `sunita` is the customer persona the
# golden path uses; `demo-admin` opens the dashboard on the laptop.
DEMO_CUSTOMER = "sunita"
DEMO_ADMIN = "demo-admin"

# Phase 2 seeds the other personas; these are the ids the seed will create.
KNOWN_DEMO_IDENTITIES: frozenset[str] = frozenset({"sunita", "ramesh", "priya", DEMO_ADMIN})

# Synthetic profiles. No real person's data appears here (plan rule 8).
# `.invalid` is reserved by RFC 2606 and can never be a real address.
_DEMO_PROFILES: dict[str, tuple[str, str]] = {
    "sunita": ("Sunita J.", "sunita.demo@spasht.invalid"),
    "ramesh": ("Ramesh Y.", "ramesh.demo@spasht.invalid"),
    "priya": ("Priya N.", "priya.demo@spasht.invalid"),
    DEMO_ADMIN: ("Demo Admin", "demo-admin@spasht.invalid"),
}


class DemoAuthError(Exception):
    """The demo headers were sent but must not be honoured.

    The message is for the log, never for the caller: which of the conditions
    failed is exactly what an attacker would like to learn.
    """


def is_demo_identity(identity: str | None) -> bool:
    """True when `identity` names a demo persona we know about."""
    return bool(identity) and identity.strip().lower() in KNOWN_DEMO_IDENTITIES


def verify_demo_key(supplied: str | None, settings: Settings) -> None:
    """Check the demo key, or raise `DemoAuthError`.

    @param supplied  The caller's `X-Demo-Key` header, if any.
    @param settings  Supplies the expected key and the environment switches.
    """
    if not settings.demo_auth:
        raise DemoAuthError("DEMO_AUTH is false")
    if not settings.is_dev:
        raise DemoAuthError(f"APP_ENV is {settings.app_env}, not dev")
    if not settings.demo_auth_key:
        raise DemoAuthError("DEMO_AUTH_KEY is not configured")
    if not supplied:
        raise DemoAuthError("no X-Demo-Key header")

    # Constant time: a byte-by-byte comparison leaks the key through timing.
    if not hmac.compare_digest(supplied, settings.demo_auth_key):
        raise DemoAuthError("X-Demo-Key does not match")


def demo_token(identity: str) -> VerifiedToken:
    """Build a `VerifiedToken` for a demo identity.

    Call only after `verify_demo_key` has passed.

    The uid is namespaced (`demo:sunita`) so a demo user can never collide with
    a real Firebase uid in the `users` table, and demo rows stay trivially
    identifiable for cleanup (decision D-015).

    `email_verified` is True because these addresses are ours and synthetic -
    that is what lets `demo-admin` reach the dashboard in dev, where the admin
    check requires a verified address.
    """
    pid = identity.strip().lower()
    if pid not in KNOWN_DEMO_IDENTITIES:
        pid = DEMO_CUSTOMER

    name, email = _DEMO_PROFILES[pid]
    return VerifiedToken(
        uid=f"demo:{pid}",
        email=email,
        name=name,
        picture=None,
        email_verified=True,
    )


def demo_persona_id(identity: str) -> str | None:
    """The persona a demo identity maps to, or None for the admin.

    `demo-admin` is a dashboard operator, not a customer, so it gets no persona
    and therefore no journey.
    """
    pid = identity.strip().lower()
    if pid == DEMO_ADMIN:
        return None
    return pid if pid in KNOWN_DEMO_IDENTITIES else DEMO_CUSTOMER
