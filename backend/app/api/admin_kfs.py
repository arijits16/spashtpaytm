"""KFS ingestion routes (build plan §8.2, phase 11).

    POST /api/admin/kfs/upload          a PDF -> a draft document with fields read
    GET  /api/admin/kfs                 the library: every document and its status
    GET  /api/admin/kfs/{id}            the fields, their confidence, the proposal
    GET  /api/admin/kfs/{id}/file       the stored PDF, for the preview pane
    POST /api/admin/kfs/{id}/verify     a named human confirms (and corrects) them
    POST /api/admin/kfs/{id}/publish    generate + guard, then activate on confirm

**Admin only, and the uploads are size- and type-checked.** `CurrentAdmin` is
the gate; the 2 MB ceiling is the body-size middleware (`/kfs/upload` is in its
allow-list) and the magic-byte check is in `kfs/ingest.py`, before the bytes are
written anywhere.

**Publish is two calls, deliberately.** `confirm: false` generates the questions
and explanation lines, runs them through the Number Guard and stores the
proposal for review; `confirm: true` activates what was reviewed. That is the
"-> review ->" in the plan's "generate -> guard -> review -> activate", and it
is why there is no single call that can put model-written text in front of a
customer.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.config import BACKEND_DIR
from app.db.models.catalog import KfsDocument, Lender, LoanOffer
from app.deps import CurrentAdmin, DbDep, SettingsDep
from app.errors import ApiError, not_found
from app.kfs import ingest
from app.kfs.parse import sanity_problems
from app.kfs.schema import LOW_CONFIDENCE
from app.security.ratelimit import client_identity, limiter

log = logging.getLogger(__name__)

router = APIRouter(tags=["admin-kfs"], prefix="/admin/kfs")

MAX_ROWS = 50


# --- response models ---------------------------------------------------------


class FieldRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    raw: str
    value: float | None
    confidence: float | None
    low: bool
    required: bool


class DocumentRow(BaseModel):
    """One row of the library list."""

    model_config = ConfigDict(extra="forbid")

    documentId: str
    lender: str
    offerId: str | None
    version: str
    status: str
    source: str
    engine: str | None
    sha256: str
    verifiedBy: str | None
    verifiedAt: str | None
    createdAt: str
    originalFilename: str | None


class DocumentDetail(DocumentRow):
    """The detail pane: fields with confidence, warnings, and the proposal."""

    model_config = ConfigDict(extra="forbid")

    fields: list[FieldRow]
    missingRequired: list[str]
    sanityProblems: list[str]
    lowConfidenceThreshold: float
    clauseCount: int
    fileUrl: str
    generated: dict[str, Any]
    canVerify: bool
    canPublish: bool
    canActivate: bool


class OfferChoice(BaseModel):
    """An offer an upload can be attached to."""

    model_config = ConfigDict(extra="forbid")

    offerId: str
    lender: str
    activeVersion: str | None


class LibraryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[DocumentRow]
    offers: list[OfferChoice]


class VerifyRequest(BaseModel):
    """`POST /admin/kfs/{id}/verify`.

    `corrections` are raw strings as a human typed them ("4,600", "18.67%"),
    parsed by the same code that parsed the extraction - so a typed value and an
    extracted one cannot be interpreted differently.
    """

    model_config = ConfigDict(extra="forbid")

    corrections: dict[str, str] = Field(default_factory=dict)


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: bool = False


class PublishResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activated: bool
    engine: str
    questions: list[dict[str, Any]]
    explain: dict[str, dict[str, str]]
    blocked: list[str]
    result: dict[str, Any] | None = None


# --- helpers -----------------------------------------------------------------


def _document(db: DbDep, document_id: uuid.UUID) -> KfsDocument:
    document = db.get(KfsDocument, document_id)
    if document is None:
        raise not_found("Key Fact Statement not found")
    return document


def _row(db: Any, document: KfsDocument) -> DocumentRow:
    lender = db.get(Lender, document.lender_id)
    extraction = document.extraction or {}
    return DocumentRow(
        documentId=str(document.id),
        lender=lender.name if lender else document.lender_id,
        offerId=document.offer_id,
        version=document.version,
        status=document.status,
        source=document.source,
        engine=extraction.get("engine"),
        sha256=document.file_sha256,
        verifiedBy=document.verified_by,
        verifiedAt=document.verified_at.isoformat() if document.verified_at else None,
        createdAt=document.created_at.isoformat(),
        originalFilename=document.original_filename,
    )


def _detail(db: Any, document: KfsDocument) -> DocumentDetail:
    from sqlalchemy import func

    from app.db.models.catalog import KfsClause

    facts = dict(document.facts or {})
    missing = ingest.missing_required(facts)
    problems = sanity_problems(facts)

    clause_count = (
        db.scalar(select(func.count(KfsClause.id)).where(KfsClause.kfs_document_id == document.id))
        or 0
    )

    generated = document.generated or {}

    return DocumentDetail(
        **_row(db, document).model_dump(),
        fields=[
            FieldRow(
                key=view.key,
                raw=view.raw,
                value=float(view.value) if view.value is not None else None,
                confidence=view.confidence,
                low=view.low,
                required=view.required,
            )
            for view in ingest.field_views(document)
        ],
        missingRequired=missing,
        sanityProblems=problems,
        lowConfidenceThreshold=LOW_CONFIDENCE,
        clauseCount=int(clause_count),
        fileUrl=f"/api/admin/kfs/{document.id}/file",
        generated=generated,
        canVerify=document.status in (ingest.STATUS_DRAFT, ingest.STATUS_VERIFIED) and not missing,
        canPublish=document.status == ingest.STATUS_VERIFIED,
        canActivate=document.status == ingest.STATUS_VERIFIED and bool(generated.get("questions")),
    )


# --- routes ------------------------------------------------------------------


@router.post("/upload", response_model=DocumentDetail)
async def upload_kfs(
    request: Request,
    admin: CurrentAdmin,
    db: DbDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    offerId: Annotated[str, Form()],
    version: Annotated[str, Form()],
) -> DocumentDetail:
    """Upload a lender's KFS PDF and read its fields.

    The document lands as `draft`: nothing it says reaches a customer until a
    human has verified the figures (§11, item 2).
    """
    limiter.enforce("turn", client_identity(request, str(admin.id)))

    data = await file.read()
    document = await ingest.ingest(
        db,
        data=data,
        filename=file.filename or "upload.pdf",
        offer_id=offerId,
        version=version,
        actor=admin.email or str(admin.id),
        settings=settings,
    )
    detail = _detail(db, document)
    db.commit()
    return detail


@router.get("", response_model=LibraryResponse)
def list_kfs(admin: CurrentAdmin, db: DbDep) -> LibraryResponse:
    """The library: every document, newest first, and the offers to upload for."""
    documents = db.scalars(
        select(KfsDocument).order_by(KfsDocument.created_at.desc()).limit(MAX_ROWS)
    ).all()

    active_versions = {
        document.offer_id: document.version
        for document in documents
        if document.status == ingest.STATUS_ACTIVE
    }

    offers = db.execute(
        select(LoanOffer, Lender).join(Lender, Lender.id == LoanOffer.lender_id)
    ).all()

    return LibraryResponse(
        documents=[_row(db, document) for document in documents],
        offers=[
            OfferChoice(
                offerId=offer.id,
                lender=lender.name,
                activeVersion=active_versions.get(offer.id),
            )
            for offer, lender in offers
        ],
    )


@router.get("/{document_id}", response_model=DocumentDetail)
def get_kfs(document_id: uuid.UUID, admin: CurrentAdmin, db: DbDep) -> DocumentDetail:
    """The extracted fields, their confidence, and any publish proposal."""
    return _detail(db, _document(db, document_id))


@router.get("/{document_id}/file")
def get_kfs_file(document_id: uuid.UUID, admin: CurrentAdmin, db: DbDep) -> FileResponse:
    """The stored PDF, for the preview pane beside the extracted fields."""
    document = _document(db, document_id)

    path = (BACKEND_DIR / document.file_path).resolve()
    allowed_root = (BACKEND_DIR / "app" / "assets").resolve()
    if not path.is_file() or not path.is_relative_to(allowed_root):
        raise not_found("Key Fact Statement file is not available")

    return FileResponse(
        path,
        media_type="application/pdf",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.post("/{document_id}/verify", response_model=DocumentDetail)
def verify_kfs(
    document_id: uuid.UUID,
    payload: VerifyRequest,
    admin: CurrentAdmin,
    db: DbDep,
) -> DocumentDetail:
    """A named human confirms the figures, correcting anything misread."""
    document = _document(db, document_id)
    ingest.verify(
        db,
        document,
        verified_by=admin.email or str(admin.id),
        corrections=payload.corrections,
    )
    detail = _detail(db, document)
    db.commit()
    return detail


@router.post("/{document_id}/publish", response_model=PublishResponse)
async def publish_kfs(
    document_id: uuid.UUID,
    payload: PublishRequest,
    request: Request,
    admin: CurrentAdmin,
    db: DbDep,
    settings: SettingsDep,
) -> PublishResponse:
    """Generate and guard the teach-back material, or activate what was reviewed.

    `confirm: false` is the review step and changes nothing a customer can see.
    `confirm: true` activates: the offer is re-priced from the verified facts,
    the previous document retires, and the reviewed questions go live.
    """
    limiter.enforce("turn", client_identity(request, str(admin.id)))
    document = _document(db, document_id)

    if payload.confirm:
        proposal = document.generated or {}
        if not proposal.get("questions"):
            raise ApiError(
                "validation_error",
                "Generate the teach-back questions first, then activate them.",
            )
        result = ingest.activate(db, document, actor=admin.email or str(admin.id))
        db.commit()
        return PublishResponse(
            activated=True,
            engine=str(proposal.get("engine") or "seeded"),
            questions=list(proposal.get("questions") or []),
            explain=dict(proposal.get("explain") or {}),
            blocked=list(proposal.get("blocked") or []),
            result=result,
        )

    proposal = await ingest.build_proposal(db, document, settings)
    db.commit()
    return PublishResponse(
        activated=False,
        engine=proposal.engine,
        questions=proposal.questions,
        explain=proposal.explain,
        blocked=proposal.blocked,
    )
