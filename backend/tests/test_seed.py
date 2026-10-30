"""The seed is idempotent and the numbers in it are the §7.2 numbers.

`make seed` runs before every rehearsal, so running it twice must be a no-op
rather than a duplicate-key error or a doubled offer list.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.catalog import KfsClause, KfsDocument, Lender, LoanOffer, TeachbackQuestion
from app.db.models.persona import AaStatement, Persona
from app.seed.run import run

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Offer id -> (rate, emi, total repay, apr), from build plan §7.2.
EXPECTED_OFFERS = {
    "offer_a": (18.67, 4_600, 55_200, 18.67),
    "offer_b": (15.99, 4_536, 54_432, 27.80),
    "offer_c": (21.00, 4_656, 55_872, 21.01),
}


@pytest.fixture(scope="module", autouse=True)
def seeded() -> None:
    """Seed twice. The second run is the actual assertion of this module."""
    run()
    run()


def test_no_duplicates_after_two_runs(db: Session) -> None:
    assert db.scalar(select(func.count()).select_from(Persona)) == 3
    assert db.scalar(select(func.count()).select_from(Lender)) == 3
    assert db.scalar(select(func.count()).select_from(LoanOffer)) == 3
    assert db.scalar(select(func.count()).select_from(KfsDocument)) == 3
    assert db.scalar(select(func.count()).select_from(TeachbackQuestion)) == 4

    # Six months of AA data per persona, not twelve.
    assert db.scalar(select(func.count()).select_from(AaStatement)) == 18
    # Nine clauses per KFS document.
    assert db.scalar(select(func.count()).select_from(KfsClause)) == 27


def test_offers_match_the_plan_table(db: Session) -> None:
    for offer_id, (rate, emi, total_repay, apr) in EXPECTED_OFFERS.items():
        offer = db.get(LoanOffer, offer_id)
        assert offer is not None, offer_id
        assert float(offer.rate_pa) == pytest.approx(rate)
        assert offer.emi == emi
        assert offer.total_repay == total_repay
        assert float(offer.apr) == pytest.approx(apr, abs=0.05)
        # Never pre-selected, anywhere (§7.2).
        assert offer.insurance_optional is True
        assert offer.insurance_premium == 750


def test_bank_b_is_the_trap(db: Session) -> None:
    """The demo's insight, asserted against the database rather than the maths:
    the lowest rate is not the lowest APR."""
    offers = db.scalars(select(LoanOffer)).all()
    lowest_rate = min(offers, key=lambda o: o.rate_pa)
    lowest_apr = min(offers, key=lambda o: o.apr)
    assert lowest_rate.id == "offer_b"
    assert lowest_apr.id == "offer_a"


def test_kfs_hash_matches_the_file_on_disk(db: Session) -> None:
    """Check #4 of receipt verification (§11.3) is only meaningful if the stored
    hash actually describes the PDF the customer can open."""
    for document in db.scalars(select(KfsDocument)).all():
        path = BACKEND_DIR / document.file_path
        assert path.is_file(), document.file_path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == document.file_sha256


def test_clause_text_carries_no_placeholders(db: Session) -> None:
    """A `{LATE_FEE}` reaching the database would be read out to a customer."""
    for clause in db.scalars(select(KfsClause)).all():
        assert "{" not in clause.text_en, clause.clause_key


def test_questions_keep_their_placeholders(db: Session) -> None:
    """The opposite rule for questions: they must stay un-filled in the bank so
    one row serves every offer and no number is hard-coded in seed text."""
    question = db.get(TeachbackQuestion, "q_late_fee")
    assert question is not None
    assert "{LATE_FEE}" in question.options[0]["text"]["mr-IN"]
    assert question.options[0]["correct"] is True
    assert db.get(TeachbackQuestion, "q_cooling_off").active is False
