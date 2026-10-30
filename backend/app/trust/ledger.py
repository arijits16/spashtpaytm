"""The receipt chain: serialised appends (build plan §11.2).

`hash = sha256(prev_hash + canonical)`. The genesis `prev_hash` is 64 zeros.
Each receipt commits to its predecessor, so altering receipt 12 invalidates 13
onwards - which is detectable without trusting anything but the chain itself.

**The hard part is concurrency.** Two journeys completing in the same instant
must not both read `last_hash` and both append, which would fork the chain into
two branches claiming the same sequence number. So every append takes a row
lock:

    SELECT ... FROM ledger_head WHERE id = 1 FOR UPDATE

Postgres serialises the lock, and the second transaction reads the first one's
committed head rather than the stale one. The test for this appends twenty
receipts in parallel and verifies the chain afterwards.

The lock is held for the duration of the insert, which is microseconds. It is a
single-row contention point by design: a chain is an ordered thing, and an
ordering that two writers can disagree about is not a chain.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.trust import GENESIS_HASH, LedgerHead, Receipt, SigningKey
from app.trust.canonical import canonicalise
from app.trust.signing import public_key_b64, sign_hash

log = logging.getLogger(__name__)

# Crockford base32: no I, L, O or U, so a receipt number read aloud over the
# phone or typed from a QR code cannot be transcribed into a different one.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# 8 characters of Crockford base32 is 40 bits.
RECEIPT_NO_LENGTH = 8

# Collisions are vanishingly unlikely at 2^40, but the column is UNIQUE so a
# collision would be an error rather than a silent overwrite; retrying is free.
_MAX_NUMBER_ATTEMPTS = 5


def receipt_number() -> str:
    """`SP-` plus 8 Crockford base32 characters from 40 random bits (§11.2)."""
    body = "".join(secrets.choice(_CROCKFORD) for _ in range(RECEIPT_NO_LENGTH))
    return f"SP-{body}"


def chain_hash(prev_hash: str, canonical: str) -> str:
    """`sha256(prev_hash + canonical)`, hex.

    The previous hash is concatenated as its hex *string*, not as bytes. That is
    an arbitrary choice but it must be the same one forever, so it is written
    down here and in §11.2 rather than left to the reader of the code.
    """
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AppendedReceipt:
    """What an append produced."""

    receipt_no: str
    seq: int
    prev_hash: str
    hash: str
    signature: str
    signing_key_id: str
    canonical: str


def ensure_public_key_registered(db: Session, settings: Settings) -> None:
    """Make sure this key's public half is in `signing_keys`.

    `/api/public-keys` serves from the table rather than from disk so that a
    rotated-out key is still published and old receipts still verify. Registering
    on first use means no separate setup step can be forgotten.
    """
    existing = db.get(SigningKey, settings.signing_key_id)
    if existing is not None:
        return
    db.add(
        SigningKey(
            key_id=settings.signing_key_id,
            public_key_b64=public_key_b64(settings),
            active=True,
        )
    )
    db.flush()


def append(
    db: Session, payload: dict[str, Any], journey_id: uuid.UUID, settings: Settings
) -> AppendedReceipt:
    """Append one receipt to the chain, under the head lock.

    The caller passes a payload **without** `receipt_no` and `seq`: both are
    assigned here, inside the lock, and written into the payload before it is
    canonicalised. They have to be inside the signed data (§11.1) or a receipt
    could be renumbered without breaking its signature.

    @returns The chain fields, for the caller to store on the `Receipt` row.
    """
    ensure_public_key_registered(db, settings)

    # FOR UPDATE: everything below runs with the chain's tip held still.
    head = db.execute(
        select(LedgerHead).where(LedgerHead.id == 1).with_for_update()
    ).scalar_one_or_none()

    if head is None:
        # Migration 0004 inserts it; this is the path for a database restored
        # from an older dump, taking the lock on the row it just created.
        db.execute(
            text(
                "INSERT INTO ledger_head (id, last_seq, last_hash) VALUES (1, 0, :h) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"h": GENESIS_HASH},
        )
        head = db.execute(
            select(LedgerHead).where(LedgerHead.id == 1).with_for_update()
        ).scalar_one()

    seq = head.last_seq + 1
    prev_hash = head.last_hash or GENESIS_HASH

    for attempt in range(_MAX_NUMBER_ATTEMPTS):
        number = receipt_number()
        full_payload = {**payload, "receipt_no": number, "seq": seq}
        canonical = canonicalise(full_payload)
        digest = chain_hash(prev_hash, canonical)
        signature, key_id = sign_hash(digest, settings)

        receipt = Receipt(
            receipt_no=number,
            seq=seq,
            journey_id=journey_id,
            payload=full_payload,
            payload_canonical=canonical,
            prev_hash=prev_hash,
            hash=digest,
            signature=signature,
            signing_key_id=key_id,
        )
        db.add(receipt)
        try:
            db.flush()
        except IntegrityError:
            # A number collision. Roll back to the savepoint and try again with
            # a new one; the head lock is still held, so `seq` stays ours.
            db.rollback()
            if attempt == _MAX_NUMBER_ATTEMPTS - 1:
                raise
            log.warning("receipt number collision, retrying")
            continue

        head.last_seq = seq
        head.last_hash = digest
        db.flush()

        log.info(
            "receipt appended",
            extra={"seq": seq, "receipt_no": number, "key_id": key_id},
        )
        return AppendedReceipt(
            receipt_no=number,
            seq=seq,
            prev_hash=prev_hash,
            hash=digest,
            signature=signature,
            signing_key_id=key_id,
            canonical=canonical,
        )

    raise RuntimeError("could not allocate a unique receipt number")


def recent(db: Session, limit: int = 10) -> list[Receipt]:
    """The last `limit` blocks, newest first (the dashboard's ledger view)."""
    return list(db.scalars(select(Receipt).order_by(Receipt.seq.desc()).limit(limit)).all())


def by_number(db: Session, receipt_no: str) -> Receipt | None:
    return db.scalar(select(Receipt).where(Receipt.receipt_no == receipt_no))


def previous_of(db: Session, receipt: Receipt) -> Receipt | None:
    """The receipt this one chains to, or None for the genesis block."""
    if receipt.seq <= 1:
        return None
    return db.scalar(select(Receipt).where(Receipt.seq == receipt.seq - 1))
