"""Dev-only demo authentication (build plan phase 1, step 4).

`X-Demo-User: sunita` stands in for a Firebase login so the demo survives a dead
venue network. It is honoured **only** when `DEMO_AUTH=true` *and* `APP_ENV=dev`
(see `Settings.demo_auth_allowed`) - never in production, whatever the header says.
"""

from __future__ import annotations

from app.auth.firebase import VerifiedToken

DEMO_HEADER = "X-Demo-User"

# Personas land in phase 2; these are the ids the seed will create.
KNOWN_DEMO_PERSONAS: frozenset[str] = frozenset({"sunita", "ramesh", "priya"})
DEFAULT_DEMO_PERSONA = "sunita"

# Synthetic profiles. No real person's data appears here (plan rule 8).
_DEMO_PROFILES: dict[str, tuple[str, str]] = {
    "sunita": ("Sunita J.", "sunita.demo@spasht.invalid"),
    "ramesh": ("Ramesh Y.", "ramesh.demo@spasht.invalid"),
    "priya": ("Priya N.", "priya.demo@spasht.invalid"),
}


def demo_token(persona_id: str) -> VerifiedToken:
    """Build a `VerifiedToken` for a demo persona.

    The uid is namespaced (`demo:sunita`) so a demo user can never collide with
    a real Firebase uid in the `users` table.
    """
    pid = persona_id.strip().lower() or DEFAULT_DEMO_PERSONA
    if pid not in KNOWN_DEMO_PERSONAS:
        pid = DEFAULT_DEMO_PERSONA

    name, email = _DEMO_PROFILES[pid]
    return VerifiedToken(
        uid=f"demo:{pid}",
        email=email,
        name=name,
        picture=None,
        email_verified=True,
    )
