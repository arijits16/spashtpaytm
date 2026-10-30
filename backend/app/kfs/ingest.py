"""Ingesting an uploaded KFS, and publishing a verified one (phase 11).

The whole path, in the order it happens:

    upload   -> a `draft` document: the file stored, its SHA-256 recorded, the
                fields extracted with per-field confidence, clauses imported
    verify   -> `verified`: a named human says the figures match the PDF
    publish  -> a proposal: generated questions and explanation lines, guarded
    activate -> `active`: the offer is re-priced from the verified facts, the
                previous document retires, the generated questions go live

**Nothing is published without verification.** It is enforced here rather than
in the route, so there is no second code path to the same transition (§11, item
2). `verified_by` and `verified_at` are what the dashboard shows and what a
regulator would ask for.

**The hash is recorded at upload, never recomputed later.** The receipt's check
#4 compares a stored hash to the file on disk; a function that re-derived it at
publish time would make the check tautological.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.sarvam_client import SarvamError, demo_mode_active
from app.config import BACKEND_DIR, Settings
from app.db.models.catalog import KfsDocument, Lender, LoanOffer, TeachbackQuestion
from app.errors import ApiError
from app.journey import events
from app.journey.loan_math import quote
from app.kfs import clauses as clause_import
from app.kfs import docai, offline
from app.kfs.parse import parse_fields, sanity_problems
from app.kfs.questions import Proposal, propose
from app.kfs.schema import LOW_CONFIDENCE, REQUIRED_KEYS

log = logging.getLogger(__name__)

# Uploads live beside the generated samples, inside the one directory
# `api/kfs.py` is allowed to serve from - so a published document opens in the
# app's PDF viewer with no new file-serving code and no new path to escape from.
UPLOAD_DIR = BACKEND_DIR / "app" / "assets" / "kfs" / "uploads"

# A two-page KFS is ~30 KB; 2 MB is the middleware's ceiling for this path.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MIN_UPLOAD_BYTES = 512

PDF_MAGIC = b"%PDF-"

STATUS_DRAFT = "draft"
STATUS_VERIFIED = "verified"
STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class FieldView:
    """One extracted field as the dashboard shows it, next to the PDF."""

    key: str
    raw: str
    value: float | int | None
    confidence: float | None
    low: bool
    required: bool


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_upload(data: bytes, filename: str) -> None:
    """Reject anything that is not a plausible PDF, before it is stored.

    Magic bytes rather than the extension or the declared content type: both of
    those are the client's claim about the file, and this is the one place that
    can check the file itself (§13.5).
    """
    if len(data) < MIN_UPLOAD_BYTES:
        raise ApiError("validation_error", "That file is too small to be a Key Fact Statement.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError("upload_too_large", "A KFS upload must be 2 MB or smaller.")
    if not data.startswith(PDF_MAGIC):
        raise ApiError("validation_error", "Only PDF files can be ingested.")
    if not filename.lower().endswith(".pdf"):
        raise ApiError("validation_error", "The file must have a .pdf extension.")


async def read_fields(
    data: bytes, filename: str, settings: Settings
) -> tuple[docai.Extraction, str]:
    """Extract with Document Intelligence, falling back to `pdfplumber`.

    Returns the extraction and the document's plain text (used for clauses).
    The fallback is not an error path to be fixed later: it is how the KFS
    library works at a venue with no network (§10.6), and the engine that read
    the document is shown on the dashboard so nobody has to guess.
    """
    text = offline.extract_text(data)

    if not demo_mode_active(settings):
        try:
            extraction = await docai.extract(data, filename, settings)
            if extraction.raw_fields:
                return extraction, text
            log.warning("document intelligence returned no fields; using the offline reader")
        except SarvamError as error:
            log.warning(
                "document intelligence failed; using the offline reader",
                extra={"kind": error.kind},
            )

    raw_fields, confidence, offline_text = offline.extract(data)
    return (
        docai.Extraction(raw_fields=raw_fields, confidence=confidence, engine=offline.ENGINE),
        text or offline_text,
    )


def field_views(document: KfsDocument) -> list[FieldView]:
    """The extracted fields, ordered as the KFS prints them."""
    extraction = document.extraction or {}
    raw = extraction.get("rawFields") or {}
    confidence = extraction.get("confidence") or {}
    facts = document.facts or {}

    from app.kfs.schema import FIELDS

    views: list[FieldView] = []
    for field in FIELDS:
        score = confidence.get(field.key)
        score = float(score) if isinstance(score, (int, float)) else None
        value = facts.get(field.key)
        views.append(
            FieldView(
                key=field.key,
                raw=str(raw.get(field.key, "")),
                value=value if isinstance(value, (int, float)) else None,
                confidence=score,
                low=score is not None and score < LOW_CONFIDENCE,
                required=field.required,
            )
        )
    return views


def missing_required(facts: dict[str, Any]) -> list[str]:
    """Required fields that could not be read. Blocks verification."""
    return [
        key
        for key in REQUIRED_KEYS
        if not isinstance(facts.get(key), (int, float)) or isinstance(facts.get(key), bool)
    ]


async def ingest(
    db: Session,
    *,
    data: bytes,
    filename: str,
    offer_id: str,
    version: str,
    actor: str,
    settings: Settings,
) -> KfsDocument:
    """Store an uploaded KFS as a `draft` document with its fields extracted."""
    validate_upload(data, filename)

    offer = db.get(LoanOffer, offer_id)
    if offer is None:
        raise ApiError("validation_error", f"Unknown offer '{offer_id}'.")

    lender = db.get(Lender, offer.lender_id)
    if lender is None:  # pragma: no cover - an offer always has a lender
        raise ApiError("validation_error", f"Offer '{offer_id}' has no lender.")

    version = version.strip()
    if not version or len(version) > 20:
        raise ApiError("validation_error", "A version like 'v4.0' is required.")

    existing = db.scalar(
        select(KfsDocument).where(KfsDocument.offer_id == offer_id, KfsDocument.version == version)
    )
    if existing is not None:
        raise ApiError(
            "validation_error",
            f"Version '{version}' already exists for {offer_id}. Use a new version string.",
        )

    digest = sha256_of(data)
    extraction, text = await read_fields(data, filename, settings)
    facts = parse_fields(extraction.raw_fields)

    # The facts a journey quotes also need the document's own identity: the
    # lender's name and the KFS version appear in spoken lines and on the
    # receipt, and neither is a figure on the page.
    facts["lender"] = lender.name
    facts["kfs_version"] = version
    facts["insurance_optional"] = True

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    document_id = uuid.uuid4()
    # Our own name, not the client's: an uploaded filename is attacker-controlled
    # and this one is used to build a path.
    stored = UPLOAD_DIR / f"{document_id}.pdf"
    stored.write_bytes(data)

    document = KfsDocument(
        id=document_id,
        lender_id=offer.lender_id,
        offer_id=offer_id,
        version=version,
        file_path=str(Path(stored).relative_to(BACKEND_DIR)),
        file_sha256=digest,
        facts=facts,
        extraction=extraction.as_metadata(),
        generated={},
        source="sarvam_docai",
        status=STATUS_DRAFT,
        original_filename=filename[:255],
        uploaded_by=actor[:200],
    )
    db.add(document)
    db.flush()

    clause_count = clause_import.replace_clauses(db, document.id, text)

    events.record(
        db,
        journey_id=None,
        actor="admin",
        event_type="kfs.uploaded",
        data={
            "documentId": str(document.id),
            "offerId": offer_id,
            "version": version,
            "engine": extraction.engine,
            "fields": len(extraction.raw_fields),
            "clauses": clause_count,
            "sha256": digest,
        },
    )

    log.info(
        "kfs uploaded",
        extra={
            "document_id": str(document.id),
            "engine": extraction.engine,
            "fields": len(extraction.raw_fields),
        },
    )
    return document


def verify(
    db: Session, document: KfsDocument, *, verified_by: str, corrections: dict[str, Any] | None
) -> KfsDocument:
    """A human confirms the figures. Optionally correcting what was misread.

    Corrections are the point of the step, not an escape hatch: an extraction
    with 0.6 confidence on the late fee is exactly the case this exists for, and
    a verification flow that could only say "yes" would be a rubber stamp.
    """
    if document.status not in (STATUS_DRAFT, STATUS_VERIFIED):
        raise ApiError(
            "validation_error",
            f"A document that is '{document.status}' cannot be verified again.",
        )

    facts = dict(document.facts or {})

    from app.kfs.schema import FIELDS_BY_KEY

    for key, raw in (corrections or {}).items():
        field = FIELDS_BY_KEY.get(key)
        if field is None:
            raise ApiError("validation_error", f"'{key}' is not a KFS field.")
        from app.kfs.parse import parse_value

        value = parse_value(raw, field.kind)
        if value is None:
            raise ApiError("validation_error", f"Could not read a number for '{key}'.")
        facts[key] = value

    missing = missing_required(facts)
    if missing:
        raise ApiError(
            "validation_error",
            "These fields still have no value: " + ", ".join(missing) + ".",
        )

    document.facts = facts
    document.status = STATUS_VERIFIED
    document.verified_by = verified_by[:200]
    document.verified_at = datetime.now(UTC)
    db.flush()

    events.record(
        db,
        journey_id=None,
        actor="admin",
        event_type="kfs.verified",
        data={
            "documentId": str(document.id),
            "verifiedBy": verified_by[:200],
            "corrected": sorted((corrections or {}).keys()),
            "sanity": sanity_problems(facts),
        },
    )
    log.info("kfs verified", extra={"document_id": str(document.id)})
    return document


async def build_proposal(db: Session, document: KfsDocument, settings: Settings) -> Proposal:
    """Generate the questions and lines a publish would activate, and store them.

    Stored on the row rather than returned only, so the review a human performs
    is against text that survives a page refresh - and so activation uses
    exactly what was reviewed rather than a second, different generation.
    """
    if document.status != STATUS_VERIFIED:
        raise ApiError(
            "validation_error",
            "Only a verified document can be published. Verify the fields first.",
        )

    proposal = await propose(db, dict(document.facts or {}), settings)
    document.generated = proposal.as_json()
    db.flush()

    events.record(
        db,
        journey_id=None,
        actor="admin",
        event_type="kfs.proposed",
        data={
            "documentId": str(document.id),
            "engine": proposal.engine,
            "questions": len(proposal.questions),
            "blocked": proposal.blocked,
        },
    )
    return proposal


def activate(db: Session, document: KfsDocument, *, actor: str) -> dict[str, Any]:
    """Make a verified, reviewed document the one a journey quotes.

    Four changes, in one transaction:

    1. the previous active document for this offer retires;
    2. this document becomes `active`;
    3. the offer is **re-priced** from the verified facts - the EMI, totals and
       APR are recomputed by `loan_math.quote` rather than taken from the PDF,
       so the catalogue can never disagree with the arithmetic a receipt is
       verified against;
    4. the generated questions replace the active set.
    """
    if document.status != STATUS_VERIFIED:
        raise ApiError("validation_error", "Verify the document before publishing it.")

    if not (document.generated or {}).get("questions"):
        raise ApiError(
            "validation_error",
            "Generate and review the teach-back questions before activating.",
        )

    facts = dict(document.facts or {})
    offer = db.get(LoanOffer, document.offer_id) if document.offer_id else None
    if offer is None:
        raise ApiError("validation_error", "This document is not attached to an offer.")

    previous = db.scalars(
        select(KfsDocument).where(
            KfsDocument.offer_id == document.offer_id,
            KfsDocument.status == STATUS_ACTIVE,
            KfsDocument.id != document.id,
        )
    ).all()
    for old in previous:
        old.status = STATUS_RETIRED

    document.status = STATUS_ACTIVE

    # Re-price from the verified terms. The PDF's own EMI and totals were
    # extracted and verified, but the catalogue stores what the code computes:
    # if the two disagree, the dashboard's sanity check already said so and the
    # receipt must still verify against our arithmetic.
    priced = quote(
        principal=int(facts["principal"]),
        annual_rate_pct=float(facts["rate_pa"]),
        tenure_months=int(facts["tenure_months"]),
        processing_fee=int(facts.get("processing_fee") or 0),
        gst_on_fee=int(facts.get("gst") or 0),
    )

    offer.principal = int(facts["principal"])
    offer.tenure_months = int(facts["tenure_months"])
    offer.rate_pa = float(facts["rate_pa"])
    offer.processing_fee = int(facts.get("processing_fee") or 0)
    offer.gst_on_fee = int(facts.get("gst") or 0)
    offer.emi = priced.emi
    offer.total_repay = priced.total_repay
    offer.total_interest = priced.total_interest
    offer.apr = priced.apr
    offer.late_fee = int(facts["late_fee"])
    offer.foreclosure_pct = float(facts["foreclosure_pct"])
    offer.cooling_off_days = int(facts["cooling_off_days"])
    offer.insurance_premium = int(facts.get("insurance_premium") or 0)
    offer.insurance_optional = True
    offer.kfs_document_id = document.id
    offer.active = True

    # Keep the document's facts consistent with the catalogue, so a spoken line
    # and the offer card cannot differ by a rupee.
    facts.update(
        {
            "emi": priced.emi,
            "total_repay": priced.total_repay,
            "total_interest": priced.total_interest,
            "total_cost": priced.total_cost,
            "apr": priced.apr,
            "net_disbursed": priced.net_disbursed,
        }
    )
    document.facts = facts

    questions = _activate_questions(db, document)

    db.flush()

    events.record(
        db,
        journey_id=None,
        actor="admin",
        event_type="kfs.activated",
        data={
            "documentId": str(document.id),
            "offerId": document.offer_id,
            "version": document.version,
            "retired": [str(old.id) for old in previous],
            "questions": questions,
            "activatedBy": actor[:200],
        },
    )
    log.info(
        "kfs activated",
        extra={"document_id": str(document.id), "offer_id": document.offer_id},
    )

    return {
        "documentId": str(document.id),
        "offerId": document.offer_id,
        "version": document.version,
        "retired": len(previous),
        "questions": questions,
        "emi": priced.emi,
        "apr": priced.apr,
    }


def _activate_questions(db: Session, document: KfsDocument) -> int:
    """Insert the reviewed questions and make them the only active set.

    The seeded rows are deactivated, not deleted. `make seed` re-activates them
    and `make demo-reset` restores the demo, so a published KFS is reversible -
    which is the difference between an ingestion feature and a one-way door.
    """
    proposal = document.generated or {}
    rows: list[dict[str, Any]] = list(proposal.get("questions") or [])

    for existing in db.scalars(
        select(TeachbackQuestion).where(TeachbackQuestion.active.is_(True))
    ).all():
        existing.active = False

    short = str(document.id)[:8]
    activated = 0

    for row in rows:
        fact_key = str(row.get("factKey") or "")
        question_id = f"q_{fact_key}_{short}"[:60]

        question = db.get(TeachbackQuestion, question_id)
        values = {
            "kfs_fact_key": fact_key,
            "sort_order": int(row.get("sortOrder") or activated + 1),
            "prompt": row.get("prompt") or {},
            "options": row.get("options") or [],
            "reexplain": row.get("reexplain") or {},
            "rubric": row.get("rubric") or {},
            "active": True,
            "source": "generated",
            "kfs_document_id": document.id,
        }

        if question is None:
            db.add(TeachbackQuestion(id=question_id, **values))
        else:
            for name, value in values.items():
                setattr(question, name, value)
        activated += 1

    return activated
