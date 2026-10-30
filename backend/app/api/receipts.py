"""Receipt routes: read, verify, and the tamper demo (build plan §8.2, §11.3).

Three audiences, three levels of detail, decided by who is asking:

* **Nobody logged in** - a judge scanning the QR code. The four checks and a
  minimal summary. No amounts, no masked identifiers, nothing about the person.
* **The owner or an admin** - the full masked payload, and the tamper editor.
* **An admin** - also the ledger and the anchors (`ledger.py`).

Verification itself is deliberately public: a trust artefact that only its
issuer can check is not worth much. The payload is what is access-controlled,
not the proof.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.journey import Journey
from app.db.models.trust import Receipt, SigningKey
from app.db.models.user import User
from app.deps import CurrentUser, DbDep, SettingsDep, optional_user
from app.errors import not_found
from app.security.ratelimit import client_identity, limiter
from app.trust import verify as verify_module
from app.trust.ledger import by_number

log = logging.getLogger(__name__)

router = APIRouter(tags=["receipts"])

# A candidate payload is an edited copy of one we issued, so it is bounded by
# what we produce. 64 KB is generous for that and small enough that the tamper
# editor cannot be used to post arbitrary bulk.
MAX_CANDIDATE_FIELDS = 200


class CheckOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ok: bool
    detail: str


class VerifyResponse(BaseModel):
    """`GET /api/receipts/{no}/verify` (§8.2)."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    checks: list[CheckOut]
    hash: str
    prevHash: str
    seq: int
    keyId: str


class CandidateRequest(BaseModel):
    """An edited copy from the website's tamper editor (§11.3)."""

    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any] = Field(max_length=MAX_CANDIDATE_FIELDS)


class CandidateResponse(VerifyResponse):
    """Verification of an edited copy, plus the field-level diff."""

    diff: list[dict[str, Any]]
    reasons: list[str]


class ReceiptSummary(BaseModel):
    """The minimal public view (§11.6).

    What a stranger with the QR code may see: that a loan was explained, in what
    language, and that the customer passed the comprehension check. No amounts
    and nothing identifying - the proof is the point, not the particulars.
    """

    model_config = ConfigDict(extra="forbid")

    receiptNo: str
    seq: int
    lender: str
    product: str
    language: str
    teachbackPassed: int
    teachbackTotal: int
    createdAt: str
    shortHash: str
    valid: bool


class ReceiptDetail(ReceiptSummary):
    """The owner's / admin's view: the whole masked payload."""

    payload: dict[str, Any]
    checks: list[CheckOut]


class PublicKeyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyId: str
    publicKeyB64: str
    active: bool


def _summary(receipt: Receipt, valid: bool) -> ReceiptSummary:
    payload = receipt.payload
    teachback = payload.get("teachback", [])
    return ReceiptSummary(
        receiptNo=receipt.receipt_no,
        seq=receipt.seq,
        lender=payload.get("lender", ""),
        product=payload.get("product", ""),
        language=payload.get("language", ""),
        teachbackPassed=sum(1 for entry in teachback if entry.get("passed")),
        teachbackTotal=len(teachback),
        createdAt=receipt.created_at.isoformat(),
        shortHash=receipt.hash[:16],
        valid=valid,
    )


def _may_see_payload(db: Session, receipt: Receipt, user: User | None) -> bool:
    """Only the customer it is about, or an admin.

    Everyone else gets the summary. A receipt names a lender, an amount and a
    comprehension score; that belongs to one person.
    """
    if user is None:
        return False
    if user.is_admin:
        return True
    owner_id = db.scalar(select(Journey.user_id).where(Journey.id == receipt.journey_id))
    return owner_id == user.id


def _load(db: Session, receipt_no: str) -> Receipt:
    receipt = by_number(db, receipt_no)
    if receipt is None:
        raise not_found("Receipt not found")
    return receipt


@router.get("/public-keys", response_model=list[PublicKeyOut])
def public_keys(db: DbDep) -> list[PublicKeyOut]:
    """The signing public keys (§8.2).

    Public and unauthenticated by design: anyone checking a receipt needs the
    key, and a public key is not a secret. Rotated-out keys stay published so
    old receipts keep verifying.
    """
    rows = db.scalars(select(SigningKey).order_by(SigningKey.created_at)).all()
    return [
        PublicKeyOut(keyId=row.key_id, publicKeyB64=row.public_key_b64, active=row.active)
        for row in rows
    ]


@router.get("/receipts/{receipt_no}", response_model=ReceiptDetail | ReceiptSummary)
def get_receipt(
    receipt_no: str,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    user: Annotated[User | None, optional_user] = None,
) -> ReceiptDetail | ReceiptSummary:
    """One receipt. Detail for the owner or an admin, summary for anyone else."""
    limiter.enforce("public", client_identity(request, str(user.id) if user else None))

    receipt = _load(db, receipt_no)
    result = verify_module.verify(db, receipt, settings)
    summary = _summary(receipt, result.valid)

    if not _may_see_payload(db, receipt, user):
        return summary

    return ReceiptDetail(
        **summary.model_dump(),
        payload=receipt.payload,
        checks=[CheckOut(**check.as_dict()) for check in result.checks],
    )


@router.get("/receipts/{receipt_no}/verify", response_model=VerifyResponse)
def verify_receipt(
    receipt_no: str, request: Request, db: DbDep, settings: SettingsDep
) -> VerifyResponse:
    """The four checks (§11.3). Public: a proof nobody can check is not a proof."""
    limiter.enforce("public", client_identity(request))

    receipt = _load(db, receipt_no)
    result = verify_module.verify(db, receipt, settings)
    return VerifyResponse(
        valid=result.valid,
        checks=[CheckOut(**check.as_dict()) for check in result.checks],
        hash=result.hash,
        prevHash=result.prev_hash,
        seq=result.seq,
        keyId=result.key_id,
    )


@router.post("/receipts/{receipt_no}/verify-candidate", response_model=CandidateResponse)
def verify_candidate_receipt(
    receipt_no: str,
    payload: CandidateRequest,
    request: Request,
    user: CurrentUser,
    db: DbDep,
    settings: SettingsDep,
) -> CandidateResponse:
    """Verify an edited copy (§11.3). **The database is never modified.**

    This is the tamper demo: an auditor changes the EMI in the browser and the
    page turns red with the exact field that moved. Authenticated and
    rate-limited because it is a hashing endpoint, not because the result is
    sensitive - the answer is always "that is not what was signed".
    """
    limiter.enforce("verify_candidate", client_identity(request, str(user.id)))

    receipt = _load(db, receipt_no)
    if not _may_see_payload(db, receipt, user):
        # Same 404 as a missing receipt: the tamper editor needs the payload, so
        # not being allowed to see it is indistinguishable from it not existing.
        raise not_found("Receipt not found")

    result = verify_module.verify_candidate(db, receipt, payload.payload, settings)
    return CandidateResponse(
        valid=result.valid,
        checks=[CheckOut(**check.as_dict()) for check in result.checks],
        hash=result.hash,
        prevHash=result.prev_hash,
        seq=result.seq,
        keyId=result.key_id,
        diff=result.diff,
        reasons=result.reasons,
    )
