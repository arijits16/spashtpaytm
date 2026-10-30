"""KFS ingestion (build plan phase 11 acceptance criteria).

Two criteria, and the second one is the one that matters:

1. **A KFS uploaded -> facts extracted -> verified -> a new journey uses the new
   facts and questions.** Asserted end to end over HTTP, finishing with a real
   journey walked to OFFERS and TEACHBACK.
2. **Nothing is published without verification; uploads are admin-only and
   size-limited.** A draft cannot be published, a customer cannot upload, and a
   non-PDF is refused before it is written anywhere.

The suite never calls Sarvam: `conftest` forces demo mode, so extraction uses
the `pdfplumber` reader and generation falls back to the seeded question bank -
which is also exactly what happens at a venue with no network (§10.6).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, settings
from app.db.models.catalog import KfsClause, KfsDocument, LoanOffer, TeachbackQuestion
from app.db.models.journey import Journey
from app.kfs import clauses as clause_import
from app.kfs import ingest, offline
from app.kfs.parse import parse_value, sanity_problems
from app.kfs.questions import _acceptable, _trilingual_ok
from app.security.demo_auth import DEMO_ADMIN
from app.security.ratelimit import limiter

SAMPLE_PDF = BACKEND_DIR / "app" / "assets" / "kfs" / "kfs_offer_b_v2.8.pdf"


@pytest.fixture(autouse=True)
def _reset_limits() -> Iterator[None]:
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def admin_headers() -> dict[str, str]:
    return {"X-Demo-User": DEMO_ADMIN, "X-Demo-Key": settings.demo_auth_key}


@pytest.fixture()
def customer_headers() -> dict[str, str]:
    return {"X-Demo-User": "sunita", "X-Demo-Key": settings.demo_auth_key}


@pytest.fixture()
def pdf_bytes() -> bytes:
    return SAMPLE_PDF.read_bytes()


@pytest.fixture()
def cleanup(db: Session) -> Iterator[list[str]]:
    """Remove documents a test created, and restore the seeded questions.

    Publishing deactivates the seeded three on purpose, so a test that publishes
    would otherwise leave every later journey asking generated questions.
    """
    created: list[str] = []
    yield created

    for document_id in created:
        document = db.get(KfsDocument, uuid.UUID(document_id))
        if document is None:
            continue
        for offer in db.scalars(
            select(LoanOffer).where(LoanOffer.kfs_document_id == document.id)
        ).all():
            offer.kfs_document_id = None

        # Journeys reference the document they were quoted from, and this
        # fixture tears down before the one that deletes test users - so the
        # reference has to be released here or the delete hits its FK.
        db.execute(
            update(Journey)
            .where(Journey.kfs_document_id == document.id)
            .values(kfs_document_id=None)
        )
        for question in db.scalars(
            select(TeachbackQuestion).where(TeachbackQuestion.kfs_document_id == document.id)
        ).all():
            db.delete(question)
        path = BACKEND_DIR / document.file_path
        db.delete(document)
        if path.is_file() and "uploads" in str(path):
            path.unlink()

    # Re-run the catalogue seed: it restores the offers' prices, their KFS
    # pointers and the seeded questions' `active` flag in one step.
    db.commit()
    from app.seed.run import seed_catalog, seed_teachback

    seed_catalog(db)
    seed_teachback(db)
    db.commit()


def _upload(
    client: TestClient,
    headers: dict[str, str],
    pdf: bytes,
    *,
    offer_id: str = "offer_b",
    version: str = "v9.0-test",
    filename: str = "bank_b_kfs.pdf",
) -> Any:
    return client.post(
        "/api/admin/kfs/upload",
        files={"file": (filename, pdf, "application/pdf")},
        data={"offerId": offer_id, "version": version},
        headers=headers,
    )


# --- the readers -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "kind", "expected"),
    [
        ("INR 1,00,000", "money", 100000),
        ("₹ 4,600", "money", 4600),
        ("18.67% (reducing balance)", "percent", 18.67),
        ("12 months", "count", 12),
        ("OPTIONAL · one-time INR 750", "money", 750),
        ("4% of principal outstanding", "percent", 4.0),
        ("Nil", "money", 0),
        ("whatever", "money", None),
        (None, "money", None),
    ],
)
def test_values_are_parsed_or_refused(raw: Any, kind: Any, expected: Any) -> None:
    """A value that cannot be read becomes None, never a guess."""
    assert parse_value(raw, kind) == expected


def test_the_offline_reader_reads_every_field(pdf_bytes: bytes) -> None:
    """`pdfplumber` on our own PDFs: the fallback the demo depends on (§10.6)."""
    raw, confidence, text = offline.extract(pdf_bytes)

    assert len(raw) == 15
    assert raw["emi"].startswith("INR")
    assert all(0 < score <= 1 for score in confidence.values())
    assert "KEY FACT STATEMENT" in text


def test_clauses_survive_the_watermark(pdf_bytes: bytes) -> None:
    """The SAMPLE watermark lands stray glyphs in the text; keys still resolve.

    Phase 8 answers "what if I close the loan early?" from `kfs_clauses`, so a
    document whose clause keys were mangled would publish and then be unable to
    answer a question about itself.
    """
    clauses = clause_import.split_clauses(offline.extract_text(pdf_bytes))
    keys = {key for key, _, _ in clauses}

    assert {"late_fee", "foreclosure", "cooling_off", "insurance_optional"} <= keys
    assert not any(key.startswith("clause_") for key in keys)


def test_sanity_checks_catch_an_inconsistent_document() -> None:
    facts = {"emi": 4600, "tenure_months": 12, "total_repay": 99999}
    assert any("total repayable" in problem for problem in sanity_problems(facts))
    assert sanity_problems({"emi": 4600, "tenure_months": 12, "total_repay": 55200}) == []


# --- generated text ---------------------------------------------------------


def test_generated_text_may_not_contain_a_number() -> None:
    """The structural half of "the AI never invents numbers".

    A literal figure is rejected even when it matches a fact, because questions
    are rendered per journey from *scaled* facts: "₹50,000" is right for the
    seeded amount and wrong for the customer who asked for ₹75,000.
    """
    facts = {"principal": 50000, "emi": 4536, "late_fee": 700}

    assert not _acceptable("You repay Rs 50,000", facts)
    assert not _acceptable("₹५००००", facts)
    assert _acceptable("You repay {PRINCIPAL}", facts)
    assert not _acceptable("{EMI} {EMI} {EMI}", facts)
    assert not _acceptable("{NOT_A_FACT}", facts)


def test_the_three_languages_must_quote_the_same_figures() -> None:
    facts = {"principal": 50000, "emi": 4536}
    assert _trilingual_ok({"mr": "{PRINCIPAL}", "hi": "{EMI}", "en": "{EMI}"}, facts) is None
    assert _trilingual_ok({"mr": "{EMI} आहे", "hi": "{EMI} है", "en": "{EMI}"}, facts) is not None


# --- authorisation and validation -------------------------------------------


def test_upload_is_admin_only(
    client: TestClient, customer_headers: dict[str, str], pdf_bytes: bytes
) -> None:
    assert _upload(client, customer_headers, pdf_bytes).status_code == 403
    assert _upload(client, {}, pdf_bytes).status_code == 401


def test_the_library_is_admin_only(client: TestClient, customer_headers: dict[str, str]) -> None:
    assert client.get("/api/admin/kfs", headers=customer_headers).status_code == 403


def test_only_a_pdf_is_accepted(client: TestClient, admin_headers: dict[str, str]) -> None:
    """Magic bytes, not the extension: both are the client's claim, and only one
    is about the file (§13.5)."""
    response = _upload(client, admin_headers, b"not a pdf" * 100, filename="evil.pdf")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_an_unknown_offer_is_refused(
    client: TestClient, admin_headers: dict[str, str], pdf_bytes: bytes
) -> None:
    assert _upload(client, admin_headers, pdf_bytes, offer_id="nope").status_code == 422


def test_a_duplicate_version_is_refused(
    client: TestClient, admin_headers: dict[str, str], pdf_bytes: bytes, cleanup: list[str]
) -> None:
    first = _upload(client, admin_headers, pdf_bytes, version="v9.1-test")
    assert first.status_code == 200
    cleanup.append(first.json()["documentId"])

    again = _upload(client, admin_headers, pdf_bytes, version="v9.1-test")
    assert again.status_code == 422


def test_an_unverified_document_cannot_be_published(
    client: TestClient, admin_headers: dict[str, str], pdf_bytes: bytes, cleanup: list[str]
) -> None:
    """Phase 11's second acceptance criterion."""
    uploaded = _upload(client, admin_headers, pdf_bytes, version="v9.2-test")
    assert uploaded.status_code == 200
    document_id = uploaded.json()["documentId"]
    cleanup.append(document_id)

    assert uploaded.json()["status"] == "draft"
    assert uploaded.json()["canPublish"] is False

    proposed = client.post(
        f"/api/admin/kfs/{document_id}/publish", json={"confirm": False}, headers=admin_headers
    )
    assert proposed.status_code == 422
    assert "verif" in proposed.json()["error"]["message"].lower()

    activated = client.post(
        f"/api/admin/kfs/{document_id}/publish", json={"confirm": True}, headers=admin_headers
    )
    assert activated.status_code == 422


def test_an_unknown_document_is_a_404(client: TestClient, admin_headers: dict[str, str]) -> None:
    unknown = "00000000-0000-4000-8000-000000000000"
    assert client.get(f"/api/admin/kfs/{unknown}", headers=admin_headers).status_code == 404


# --- the whole path ---------------------------------------------------------


def test_upload_verify_publish_then_a_journey_uses_the_new_facts(
    client: TestClient,
    db: Session,
    admin_headers: dict[str, str],
    customer_headers: dict[str, str],
    pdf_bytes: bytes,
    cleanup: list[str],
) -> None:
    """Phase 11's first acceptance criterion, end to end.

    Bank B's KFS is uploaded with a corrected late fee, verified, published and
    activated - and then a brand-new journey quotes the corrected figure and
    asks the activated questions.
    """
    uploaded = _upload(client, admin_headers, pdf_bytes, version="v9.3-test")
    assert uploaded.status_code == 200, uploaded.text
    detail = uploaded.json()
    document_id = detail["documentId"]
    cleanup.append(document_id)

    # Extracted, with every required field read and the clauses imported.
    assert detail["missingRequired"] == []
    assert detail["clauseCount"] >= 8
    assert detail["engine"] in ("pdfplumber", "sarvam_docai")
    assert detail["sha256"] == ingest.sha256_of(pdf_bytes)
    assert db.scalar(select(KfsClause).where(KfsClause.kfs_document_id == uuid.UUID(document_id)))

    # The stored file is inside the one directory the file routes may serve.
    stored = (BACKEND_DIR / db.get(KfsDocument, uuid.UUID(document_id)).file_path).resolve()
    assert stored.is_relative_to((BACKEND_DIR / "app" / "assets").resolve())
    assert (
        client.get(f"/api/admin/kfs/{document_id}/file", headers=admin_headers).status_code == 200
    )

    # A human verifies, correcting the late fee the lender revised.
    verified = client.post(
        f"/api/admin/kfs/{document_id}/verify",
        json={"corrections": {"late_fee": "750"}},
        headers=admin_headers,
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "verified"
    assert verified.json()["verifiedBy"]
    assert verified.json()["verifiedAt"]
    assert verified.json()["canPublish"] is True

    # Generate and guard. In demo mode this is the seeded bank, which is the
    # same material the golden path uses.
    proposed = client.post(
        f"/api/admin/kfs/{document_id}/publish", json={"confirm": False}, headers=admin_headers
    )
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["activated"] is False
    assert len(proposed.json()["questions"]) == 3
    assert set(proposed.json()["explain"]) == {"explain_1", "explain_2", "explain_3"}

    # Nothing a customer sees has changed yet.
    assert db.get(KfsDocument, uuid.UUID(document_id)).status == "verified"

    activated = client.post(
        f"/api/admin/kfs/{document_id}/publish", json={"confirm": True}, headers=admin_headers
    )
    assert activated.status_code == 200, activated.text
    result = activated.json()["result"]
    assert result["questions"] == 3
    assert result["retired"] >= 1

    db.expire_all()
    document = db.get(KfsDocument, uuid.UUID(document_id))
    offer = db.get(LoanOffer, "offer_b")
    assert document.status == "active"
    assert offer.kfs_document_id == document.id
    # The corrected figure reached the catalogue.
    assert offer.late_fee == 750
    # And the offer was re-priced by our own arithmetic, not by the PDF's.
    assert offer.emi == result["emi"]

    # The activated questions are the only active set.
    active = db.scalars(select(TeachbackQuestion).where(TeachbackQuestion.active.is_(True))).all()
    assert len(active) == 3
    assert all(question.kfs_document_id == document.id for question in active)

    # A new journey quotes the new facts and asks the new questions.
    started = client.post(
        "/api/journeys",
        json={"product": "personal_loan", "language": "en-IN"},
        headers=customer_headers,
    )
    assert started.status_code == 200, started.text
    journey_id = started.json()["journeyId"]

    def turn(payload: dict[str, Any]) -> Any:
        response = client.post(
            f"/api/journeys/{journey_id}/turn",
            json={"clientTurnId": str(uuid.uuid4()), "input": payload},
            headers=customer_headers,
        )
        assert response.status_code == 200, response.text
        return response.json()

    turn({"type": "tap", "action": {"name": "amount", "amount": 50000}})
    turn(
        {
            "type": "tap",
            "action": {
                "name": "consents",
                "grants": {"fetch_digilocker": True, "fetch_account_aggregator": True},
            },
        }
    )
    body = turn({"type": "tap", "action": {"name": "confirm_details"}})

    assert body["step"] == "OFFERS"
    offers = {entry["offerId"]: entry for entry in body["card"]["data"]["offers"]}
    assert offers["offer_b"]["kfsUrl"].endswith(f"{document.id}/file")

    # The teach-back uses the activated questions.
    turn({"type": "tap", "action": {"name": "select_offer", "offerId": "offer_b"}})
    # "yes" is how the customer leaves EXPLAIN_KFS, the same way the golden-path
    # walker does it in `test_journey.py`.
    quiz = turn({"type": "text", "text": "yes"})
    for _ in range(3):
        if quiz["step"] == "TEACHBACK":
            break
        quiz = turn({"type": "text", "text": "yes"})

    assert quiz["step"] == "TEACHBACK"
    assert quiz["card"]["data"]["questionId"].endswith(str(document.id)[:8])
