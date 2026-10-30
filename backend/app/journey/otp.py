"""OTP challenges (build plan §13.6).

The code is six digits from `secrets.randbelow`, stored only as
HMAC-SHA256(`OTP_PEPPER`, code) and compared in constant time. It expires in
five minutes and locks after three wrong attempts.

**The code is never logged and never spoken.** The assistant's own OTP line says
so out loud ("तो कधीच बोलून सांगू नका"), because a voice product that reads an
OTP aloud teaches a habit that gets people robbed. In dev with `OTP_DEMO=true`
the code is returned in the response so the demo works without a real SMS, and
the app shows it as an obvious fake-SMS banner.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.journey import OtpChallenge

log = logging.getLogger(__name__)

CODE_LENGTH = 6
TTL_SECONDS = 300
MAX_ATTEMPTS = 3


def _hash(code: str, settings: Settings) -> str:
    """HMAC the code with the pepper.

    A pepper rather than a plain hash: six digits is a million possibilities,
    which a GPU exhausts instantly, so the secret is what makes a stolen
    database row useless.
    """
    pepper = settings.otp_pepper or "dev-otp-pepper"
    return hmac.new(pepper.encode(), code.encode(), hashlib.sha256).hexdigest()


def generate_code() -> str:
    """A cryptographically random 6-digit code.

    `secrets`, not `random`: a predictable OTP is not an OTP.
    """
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def issue(
    db: Session, journey_id: uuid.UUID, settings: Settings
) -> tuple[OtpChallenge, str | None]:
    """Create a challenge. Returns it and the demo code, if one may be shown.

    Any earlier unverified challenge for this journey is locked first, so
    requesting a new code cannot be used to multiply the attempt budget.
    """
    for previous in db.scalars(
        select(OtpChallenge).where(
            OtpChallenge.journey_id == journey_id,
            OtpChallenge.verified_at.is_(None),
            OtpChallenge.locked.is_(False),
        )
    ).all():
        previous.locked = True

    code = generate_code()
    challenge = OtpChallenge(
        journey_id=journey_id,
        code_hmac=_hash(code, settings),
        expires_at=datetime.now(UTC) + timedelta(seconds=TTL_SECONDS),
        attempts=0,
        locked=False,
    )
    db.add(challenge)
    db.flush()

    # Only in dev, only when explicitly switched on (§13.6).
    demo_code = code if (settings.otp_demo and settings.is_dev) else None
    return challenge, demo_code


class OtpResult:
    """Why a verification failed, for the caller to turn into a message.

    Deliberately not an exception: a wrong OTP is an expected part of the
    journey, not an error condition.
    """

    OK = "ok"
    WRONG = "wrong"
    EXPIRED = "expired"
    LOCKED = "locked"
    MISSING = "missing"


def current(db: Session, journey_id: uuid.UUID) -> OtpChallenge | None:
    """The newest challenge for a journey, verified or not."""
    return db.scalar(
        select(OtpChallenge)
        .where(OtpChallenge.journey_id == journey_id)
        .order_by(OtpChallenge.created_at.desc())
        .limit(1)
    )


def verify(db: Session, journey_id: uuid.UUID, code: str, settings: Settings) -> str:
    """Check a code against the newest challenge. Returns an `OtpResult`.

    The attempt is counted before the comparison, so a crash between the two
    cannot hand back a free guess.
    """
    challenge = current(db, journey_id)
    if challenge is None:
        return OtpResult.MISSING
    if challenge.verified_at is not None:
        # Already verified: treat a repeat as success so a retried request after
        # a dropped connection does not look like a failure to the customer.
        return OtpResult.OK
    if challenge.locked:
        return OtpResult.LOCKED
    if challenge.expires_at <= datetime.now(UTC):
        return OtpResult.EXPIRED

    challenge.attempts += 1
    if challenge.attempts >= MAX_ATTEMPTS:
        challenge.locked = True
    db.flush()

    if hmac.compare_digest(challenge.code_hmac, _hash(code, settings)):
        challenge.verified_at = datetime.now(UTC)
        challenge.locked = False
        db.flush()
        return OtpResult.OK

    return OtpResult.LOCKED if challenge.locked else OtpResult.WRONG


def attempts_left(challenge: OtpChallenge | None) -> int:
    if challenge is None:
        return MAX_ATTEMPTS
    return max(0, MAX_ATTEMPTS - challenge.attempts)
