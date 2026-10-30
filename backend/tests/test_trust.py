"""The trust layer (build plan phase 6 acceptance criteria).

Four claims are tested here, and they are the claims the product makes about
itself:

* a receipt we issue verifies;
* an **edited** receipt does not, and the stored one is untouched;
* a **broken chain** is detected, not just a broken payload;
* **twenty parallel appends** leave the chain valid, which is the only way to
  know the head lock is doing its job.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.trust import GENESIS_HASH, Receipt
from app.db.session import SessionLocal
from app.trust.canonical import canonicalise, diff
from app.trust.ledger import append, chain_hash, receipt_number
from app.trust.merkle import merkle_root
from app.trust.signing import public_key_b64, sign_hash, verify_signature
from app.trust.verify import verify, verify_candidate, verify_chain


def _make_journey(db: Session, suffix: str) -> uuid.UUID:
    """A minimal journey a receipt can hang off."""
    user_id = uuid.uuid4()
    journey_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO users (id, firebase_uid, email, preferred_language, session_kind) "
            "VALUES (:id, :uid, :email, 'mr-IN', 'demo')"
        ),
        {
            "id": user_id,
            "uid": f"test:trust-{suffix}",
            "email": f"trust-{suffix}@example.invalid",
        },
    )
    db.execute(
        text(
            "INSERT INTO journeys (id, user_id, persona_id, language, step, status, context) "
            "VALUES (:id, :uid, 'sunita', 'mr-IN', 'RECEIPT', 'completed', '{}'::jsonb)"
        ),
        {"id": journey_id, "uid": user_id},
    )
    db.commit()
    return journey_id


def _payload(**overrides: object) -> dict:
    base = {
        "journey_id": str(uuid.uuid4()),
        "customer_display": "Sunita J.",
        "lender": "Partner NBFC A",
        "language": "mr-IN",
        "terms": {"emi": 4_600, "total_repay": 55_200},
        "teachback": [{"q": "q_late_fee", "attempts": 1, "passed": True}],
    }
    base.update(overrides)
    return base


# --- the primitives ---------------------------------------------------------


def test_canonical_form_is_stable_and_readable() -> None:
    """Key order must not matter, and Devanagari must survive un-escaped."""
    left = canonicalise({"b": 1, "a": "सुनीता"})
    right = canonicalise({"a": "सुनीता", "b": 1})
    assert left == right == '{"a":"सुनीता","b":1}'


def test_hash_commits_to_both_payload_and_position() -> None:
    """Same payload, different predecessor -> different hash.

    This is what stops a valid receipt being lifted out and replayed elsewhere
    in the chain.
    """
    canonical = canonicalise(_payload())
    assert chain_hash(GENESIS_HASH, canonical) != chain_hash("a" * 64, canonical)


def test_receipt_numbers_avoid_confusable_characters() -> None:
    """Crockford base32: no I, L, O or U, so a number read aloud survives."""
    for _ in range(50):
        number = receipt_number()
        assert number.startswith("SP-")
        assert len(number) == 11
        assert not set("ILOU") & set(number[3:])


def test_signature_verifies_and_a_changed_hash_does_not() -> None:
    signature, key_id = sign_hash("a" * 64, settings)
    public = public_key_b64(settings)
    assert key_id == settings.signing_key_id
    assert verify_signature("a" * 64, signature, public) is True
    assert verify_signature("b" * 64, signature, public) is False


def test_signature_from_the_wrong_key_is_rejected() -> None:
    """Phase 6 acceptance: a wrong-key signature must fail."""
    from nacl import signing as nacl_signing

    other = nacl_signing.SigningKey.generate()
    import base64

    foreign_public = base64.b64encode(bytes(other.verify_key)).decode()
    signature, _ = sign_hash("a" * 64, settings)
    assert verify_signature("a" * 64, signature, foreign_public) is False


def test_merkle_root_handles_an_odd_count() -> None:
    """The last leaf is duplicated, so a root exists for any count."""
    assert merkle_root([]) is None
    assert merkle_root(["a" * 64]) == "a" * 64
    three = merkle_root(["a" * 64, "b" * 64, "c" * 64])
    four = merkle_root(["a" * 64, "b" * 64, "c" * 64, "c" * 64])
    assert three == four


def test_diff_reports_field_paths() -> None:
    changes = diff({"terms": {"emi": 4_600}}, {"terms": {"emi": 4_000}})
    assert changes == [{"path": "terms.emi", "from": 4_600, "to": 4_000}]


# --- the chain --------------------------------------------------------------


@pytest.fixture()
def appended(db: Session):
    """One real receipt in the chain."""
    journey_id = _make_journey(db, "append")
    result = append(db, _payload(journey_id=str(journey_id)), journey_id, settings)
    db.commit()
    receipt = db.scalar(select(Receipt).where(Receipt.receipt_no == result.receipt_no))
    assert receipt is not None
    return receipt


def test_an_issued_receipt_verifies(db: Session, appended: Receipt) -> None:
    result = verify(db, appended, settings)
    # The KFS check fails here because this synthetic payload names no KFS; the
    # three cryptographic checks are what this test is about.
    by_name = {check.name: check.ok for check in result.checks}
    assert by_name["payload_hash"] is True
    assert by_name["chain_link"] is True
    assert by_name["signature"] is True


def test_tampering_is_detected_and_the_stored_receipt_is_untouched(
    db: Session, appended: Receipt
) -> None:
    """The demo: edit the EMI in the browser, the page turns red (§11.3)."""
    original_hash = appended.hash

    candidate = {**appended.payload}
    candidate["terms"] = {**candidate["terms"], "emi": 4_000}

    result = verify_candidate(db, appended, candidate, settings)
    assert result.valid is False
    assert any("terms.emi" in reason for reason in result.reasons)

    by_name = {check.name: check.ok for check in result.checks}
    assert by_name["payload_hash"] is False
    assert by_name["signature"] is False

    # Nothing was written: the point of the demo is that the real one survives.
    db.expire_all()
    stored = db.scalar(select(Receipt).where(Receipt.id == appended.id))
    assert stored is not None
    assert stored.hash == original_hash
    assert stored.payload["terms"]["emi"] == 4_600


def test_an_unedited_candidate_still_verifies(db: Session, appended: Receipt) -> None:
    """The editor's starting state must not already be red.

    Only the cryptographic checks are asserted: this synthetic payload names no
    KFS document, so check #4 correctly reports that - and a real receipt from
    the golden path is checked end to end by `play_golden_path.py`.
    """
    result = verify_candidate(db, appended, dict(appended.payload), settings)
    assert result.diff == []
    by_name = {check.name: check.ok for check in result.checks}
    assert by_name["payload_hash"] is True
    assert by_name["chain_link"] is True
    assert by_name["signature"] is True


def test_a_broken_chain_link_is_detected(db: Session) -> None:
    """Phase 6 acceptance: chain-break detection.

    The append-only trigger means the stored chain cannot be edited to create a
    break, which is the guarantee working - so the break is constructed in
    memory, on a copy, and `_check_chain` is asked about it.
    """
    from app.trust.verify import _check_chain

    first_journey = _make_journey(db, "chain-1")
    second_journey = _make_journey(db, "chain-2")
    append(db, _payload(journey_id=str(first_journey)), first_journey, settings)
    second = append(db, _payload(journey_id=str(second_journey)), second_journey, settings)
    db.commit()

    receipt = db.scalar(select(Receipt).where(Receipt.receipt_no == second.receipt_no))
    assert receipt is not None
    assert _check_chain(db, receipt).ok is True

    # Detach the copy from the session so the forged prev_hash is never flushed.
    db.expunge(receipt)
    receipt.prev_hash = "f" * 64
    broken = _check_chain(db, receipt)
    assert broken.ok is False
    assert "chain is broken" in broken.detail


def test_twenty_parallel_appends_keep_the_chain_valid(db: Session) -> None:
    """Phase 6 acceptance. The head lock is the only thing making this pass.

    Each worker gets its own session and connection, so these are twenty real
    concurrent transactions contending for `ledger_head`. Without the
    `FOR UPDATE`, several would read the same `last_seq` and the chain would
    fork - which the walk at the end would report as a gap or a bad link.
    """
    journeys = [_make_journey(db, f"parallel-{index}") for index in range(20)]

    def worker(journey_id: uuid.UUID) -> str:
        with SessionLocal() as session:
            result = append(session, _payload(journey_id=str(journey_id)), journey_id, settings)
            session.commit()
            return result.hash

    with ThreadPoolExecutor(max_workers=20) as pool:
        hashes = list(pool.map(worker, journeys))

    assert len(set(hashes)) == 20, "two appends produced the same hash"

    ok, problems = verify_chain(db)
    assert ok, problems

    # Sequence numbers are gap-free, which a per-receipt check cannot see.
    seqs = db.scalars(select(Receipt.seq).order_by(Receipt.seq)).all()
    assert list(seqs) == list(range(1, len(seqs) + 1))


def test_receipts_are_append_only_in_the_database(db: Session, appended: Receipt) -> None:
    """The last line of defence: even with SQL access, a receipt cannot change."""
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(
            text("UPDATE receipts SET hash = :h WHERE id = :id"),
            {"h": "0" * 64, "id": appended.id},
        )
    db.rollback()
