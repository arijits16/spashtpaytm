"""Ledger and anchor routes (build plan §8.2, §12).

Admin-only, because the chain is the compliance view: who was issued what, in
order. The individual receipts are public and verifiable; the *list* of them is
not, since it would otherwise be a feed of every loan the system has explained.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.deps import CurrentAdmin, DbDep
from app.trust import merkle
from app.trust.ledger import recent
from app.trust.verify import verify_chain

router = APIRouter(tags=["ledger"])

# §12: "the last 10 blocks as linked cards".
DEFAULT_BLOCKS = 10
MAX_BLOCKS = 100


class LedgerBlock(BaseModel):
    """One block, with both hashes so the UI can draw prev -> hash links."""

    model_config = ConfigDict(extra="forbid")

    seq: int
    receiptNo: str
    prevHash: str
    hash: str
    keyId: str
    createdAt: str


class AnchorOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: str
    merkleRoot: str
    receiptCount: int


class LedgerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocks: list[LedgerBlock]
    lastSeq: int

    # Whether the whole chain walks cleanly, not just each block on its own: a
    # gap in `seq` is invisible block-by-block (section 11.3).
    chainValid: bool
    problems: list[str]
    todayAnchor: AnchorOut | None


@router.get("/ledger", response_model=LedgerResponse)
def get_ledger(admin: CurrentAdmin, db: DbDep, limit: int = DEFAULT_BLOCKS) -> LedgerResponse:
    """Recent blocks, the chain's verdict, and today's anchor."""
    blocks = recent(db, min(max(1, limit), MAX_BLOCKS))
    ok, problems = verify_chain(db)

    today = datetime.now(UTC).date()
    anchor = merkle.upsert_anchor(db, today)
    db.commit()

    return LedgerResponse(
        blocks=[
            LedgerBlock(
                seq=block.seq,
                receiptNo=block.receipt_no,
                prevHash=block.prev_hash,
                hash=block.hash,
                keyId=block.signing_key_id,
                createdAt=block.created_at.isoformat(),
            )
            for block in blocks
        ],
        lastSeq=blocks[0].seq if blocks else 0,
        chainValid=ok,
        problems=problems,
        todayAnchor=(
            AnchorOut(
                day=anchor.day.isoformat(),
                merkleRoot=anchor.merkle_root,
                receiptCount=anchor.receipt_count,
            )
            if anchor
            else None
        ),
    )


@router.get("/ledger/anchors", response_model=list[AnchorOut])
def get_anchors(admin: CurrentAdmin, db: DbDep) -> list[AnchorOut]:
    """The last week of daily Merkle roots (§11.4)."""
    merkle.upsert_anchor(db, datetime.now(UTC).date())
    db.commit()
    return [
        AnchorOut(
            day=anchor.day.isoformat(),
            merkleRoot=anchor.merkle_root,
            receiptCount=anchor.receipt_count,
        )
        for anchor in merkle.recent_anchors(db)
    ]
