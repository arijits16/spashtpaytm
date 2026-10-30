"""The evidence tables refuse to be rewritten (build plan §6, §13.9).

A receipt is only evidence if nobody - including this application, including a
developer with a psql prompt - can quietly change what the customer was told or
agreed to. These tests are the proof that the guarantee is real and not just a
convention everyone promises to follow.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

APPEND_ONLY_TABLES = ("audit_log", "consents", "teachback_attempts", "receipts")


def _make_journey(db: Session) -> uuid.UUID:
    """A throwaway journey to hang evidence rows off, plus the user it needs."""
    user_id = uuid.uuid4()
    journey_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO users (id, firebase_uid, email, preferred_language, session_kind) "
            "VALUES (:id, :uid, :email, 'mr-IN', 'demo')"
        ),
        {"id": user_id, "uid": f"test:append-{user_id}", "email": "append@example.invalid"},
    )
    db.execute(
        text(
            "INSERT INTO journeys (id, user_id, persona_id, language, step, status, context) "
            "VALUES (:id, :uid, 'sunita', 'mr-IN', 'INTRO', 'active', '{}'::jsonb)"
        ),
        {"id": journey_id, "uid": user_id},
    )
    db.commit()
    return journey_id


@pytest.fixture()
def journey_id(db: Session) -> Iterator[uuid.UUID]:
    """A journey to hang evidence off, cleaned up by the autouse `clean_users`
    fixture - which has to suspend the triggers to do it, because even a
    cascading delete of a whole journey is refused while they are on."""
    yield _make_journey(db)
    db.rollback()


def test_audit_log_rejects_update_and_delete(db: Session, journey_id: uuid.UUID) -> None:
    db.execute(
        text(
            "INSERT INTO audit_log (journey_id, actor, event_type, step, data) "
            "VALUES (:j, 'customer', 'step.entered', 'OFFERS', '{}'::jsonb)"
        ),
        {"j": journey_id},
    )
    db.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(
            text("UPDATE audit_log SET event_type = 'tampered' WHERE journey_id = :j"),
            {"j": journey_id},
        )
    db.rollback()

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM audit_log WHERE journey_id = :j"), {"j": journey_id})
    db.rollback()


def test_consents_cannot_be_flipped(db: Session, journey_id: uuid.UUID) -> None:
    """The one that matters most: a declined consent must not become a granted one."""
    db.execute(
        text(
            "INSERT INTO consents (journey_id, purpose, granted, default_value, method, evidence) "
            "VALUES (:j, 'insurance_addon', false, false, 'tap', '{}'::jsonb)"
        ),
        {"j": journey_id},
    )
    db.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(
            text("UPDATE consents SET granted = true WHERE journey_id = :j"),
            {"j": journey_id},
        )
    db.rollback()

    # Withdrawing a consent is an insert, not an update - the trail keeps both.
    db.execute(
        text(
            "INSERT INTO consents (journey_id, purpose, granted, default_value, method, evidence) "
            "VALUES (:j, 'insurance_addon', true, false, 'tap', '{}'::jsonb)"
        ),
        {"j": journey_id},
    )
    db.commit()
    rows = (
        db.execute(
            text("SELECT granted FROM consents WHERE journey_id = :j ORDER BY id"),
            {"j": journey_id},
        )
        .scalars()
        .all()
    )
    assert rows == [False, True]


def test_teachback_attempts_keep_wrong_answers(db: Session, journey_id: uuid.UUID) -> None:
    """A wrong first attempt is the signal the dashboard charts. It cannot be
    deleted to make the completion numbers look better."""
    db.execute(
        text(
            "INSERT INTO teachback_attempts "
            "(journey_id, question_id, attempt_no, answer_type, answer_value, is_correct, grader) "
            "VALUES (:j, 'q_late_fee', 1, 'option', 'b', false, 'rule')"
        ),
        {"j": journey_id},
    )
    db.commit()

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(
            text("DELETE FROM teachback_attempts WHERE journey_id = :j"),
            {"j": journey_id},
        )
    db.rollback()


def test_every_evidence_table_has_the_trigger(db: Session) -> None:
    """Guards against a future migration adding a table and forgetting it."""
    installed = set(
        db.execute(
            text(
                "SELECT event_object_table FROM information_schema.triggers "
                "WHERE trigger_name LIKE '%_append_only'"
            )
        ).scalars()
    )
    assert set(APPEND_ONLY_TABLES) <= installed
