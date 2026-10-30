"""Audit events (build plan §9, §6 `audit_log`).

Every engine transition writes one row. The trail is append-only, so what it
records is what happened - and the dashboard's funnel, the journey detail
timeline and the rescue scheduler all read from it rather than from any state we
could have overwritten.

**What must never go in `data`.** No transcript, no OTP, no token, no secret, no
unmasked identifier. The redaction rules of §13.8 apply here exactly as they do
to logs: an audit row is read by an admin on a laptop, and the transcript it
might have contained lives encrypted in `conversation_turns` instead.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models.journey import AuditLog
from app.security.request_id import get_request_id

log = logging.getLogger(__name__)

# Event types, named so the dashboard can group them without string matching.
STEP_ENTERED = "step.entered"
TURN_RECEIVED = "turn.received"
TURN_REPLAYED = "turn.replayed"
CONSENT_RECORDED = "consent.recorded"
PREFILL_COMPLETED = "prefill.completed"
OFFER_SELECTED = "offer.selected"
SUITABILITY_DECIDED = "suitability.decided"
TEACHBACK_ANSWERED = "teachback.answered"
TEACHBACK_PASSED = "teachback.passed"
TEACHBACK_FAILED = "teachback.failed"
TERMS_ACCEPTED = "terms.accepted"
CONSENT_LOCK_REFUSED = "consent.lock_refused"
OTP_SENT = "otp.sent"
OTP_VERIFIED = "otp.verified"
OTP_FAILED = "otp.failed"
RECEIPT_CREATED = "receipt.created"
HANDOFF = "journey.handoff"
JOURNEY_STARTED = "journey.started"
JOURNEY_COMPLETED = "journey.completed"
JOURNEY_RESUMED = "journey.resumed"
GUARD_BLOCKED = "guard.blocked"
LANGUAGE_SWITCHED = "language.switched"
RESCUE_CREATED = "rescue.created"
RESCUE_ACCEPTED = "rescue.accepted"


def record(
    db: Session,
    *,
    journey_id: uuid.UUID | None,
    actor: str,
    event_type: str,
    step: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Append one audit row.

    Flushed but not committed: the event belongs to the same transaction as the
    transition it describes, so a rolled-back turn leaves no trace of having
    happened. Half-written history is worse than none.

    @param actor  'customer' | 'demo' | 'system' | 'agent' | 'admin'.
    """
    db.add(
        AuditLog(
            journey_id=journey_id,
            actor=actor,
            event_type=event_type,
            step=step,
            data=data or {},
            request_id=get_request_id(),
        )
    )
    db.flush()
