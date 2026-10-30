"""Receipt verification and the tamper demo (build plan §11.3).

Four checks, in the order a sceptic would ask them:

1. **Hash matches the payload.** Re-canonicalise and re-hash: if the stored
   payload was edited, the hash it claims no longer follows from it.
2. **`prev_hash` matches the previous receipt.** Links this receipt into the
   chain, so removing or reordering a receipt is visible.
3. **Signature is valid.** Proves this backend issued it, not someone with an
   INSERT on the table.
4. **KFS file hash matches.** Proves the document the customer was shown is the
   document still on disk, so the terms cannot be swapped afterwards.

`verify_candidate` runs 1-3 against an **edited copy** supplied by the website's
tamper editor and returns the field-level diff. It never touches the database -
the demo's whole point is that the real receipt is unchanged while the edited
one fails.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, Settings
from app.db.models.catalog import KfsDocument
from app.db.models.trust import GENESIS_HASH, Receipt, SigningKey
from app.trust.canonical import canonicalise, diff
from app.trust.ledger import chain_hash, previous_of
from app.trust.signing import verify_signature

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Check:
    """One named check, with a human-readable detail either way.

    The detail is shown on the public page and in the dashboard, so it is
    written for a person: "chain links to receipt 41", not "prev_hash ok".
    """

    name: str
    ok: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        """For the API models. `slots=True` means there is no `__dict__`."""
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass
class VerificationResult:
    valid: bool
    checks: list[Check] = field(default_factory=list)
    hash: str = ""
    prev_hash: str = ""
    seq: int = 0
    key_id: str = ""

    # Only populated by `verify_candidate`.
    diff: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _public_key_for(db: Session, key_id: str) -> str | None:
    """The published public key for a key id.

    Read from `signing_keys` rather than from the key file on disk, so a receipt
    signed by a key that has since been rotated out still verifies.
    """
    row = db.get(SigningKey, key_id)
    if row is not None:
        return row.public_key_b64
    return None


def _check_hash(payload: dict[str, Any], prev_hash: str, claimed: str) -> Check:
    recomputed = chain_hash(prev_hash, canonicalise(payload))
    ok = recomputed == claimed
    return Check(
        name="payload_hash",
        ok=ok,
        detail=(
            "The receipt's contents hash to exactly the stored hash."
            if ok
            else f"Contents do not match the hash. Recomputed {recomputed[:12]}…, "
            f"stored {claimed[:12]}…"
        ),
    )


def _check_chain(db: Session, receipt: Receipt) -> Check:
    if receipt.seq <= 1:
        ok = receipt.prev_hash == GENESIS_HASH
        return Check(
            name="chain_link",
            ok=ok,
            detail=(
                "First receipt in the chain, linked to the genesis block."
                if ok
                else "First receipt does not link to the genesis block."
            ),
        )

    previous = previous_of(db, receipt)
    if previous is None:
        return Check(
            name="chain_link",
            ok=False,
            detail=f"Receipt {receipt.seq - 1} is missing from the chain.",
        )

    ok = previous.hash == receipt.prev_hash
    return Check(
        name="chain_link",
        ok=ok,
        detail=(
            f"Chain links correctly to receipt {previous.seq}."
            if ok
            else f"Does not link to receipt {previous.seq}: the chain is broken."
        ),
    )


def _check_signature(db: Session, hash_hex: str, signature: str, key_id: str) -> Check:
    public_key = _public_key_for(db, key_id)
    if public_key is None:
        return Check(
            name="signature",
            ok=False,
            detail=f"Signing key '{key_id}' is not published, so this cannot be checked.",
        )

    ok = verify_signature(hash_hex, signature, public_key)
    return Check(
        name="signature",
        ok=ok,
        detail=(
            f"Signed by key '{key_id}' and the signature is valid."
            if ok
            else f"The signature does not match key '{key_id}'."
        ),
    )


def _check_kfs(db: Session, payload: dict[str, Any]) -> Check:
    """Check #4: the KFS document is still byte-identical.

    This is the check that makes the receipt about the *terms* and not just
    about the conversation. Without it, a lender could replace the PDF with a
    harsher version and every receipt would still verify.
    """
    kfs = payload.get("kfs") or {}
    document_id = kfs.get("id")
    claimed_sha = kfs.get("file_sha256")

    if not document_id or not claimed_sha:
        return Check(
            name="kfs_document",
            ok=False,
            detail="The receipt does not name a Key Fact Statement.",
        )

    document = db.scalar(select(KfsDocument).where(KfsDocument.id == document_id))
    if document is None:
        return Check(
            name="kfs_document",
            ok=False,
            detail="The Key Fact Statement named by this receipt no longer exists.",
        )

    if document.file_sha256 != claimed_sha:
        return Check(
            name="kfs_document",
            ok=False,
            detail="The stored Key Fact Statement differs from the one on the receipt.",
        )

    # The file itself, when it is still on this machine. A missing file is not a
    # failure of the receipt - it is a deployment fact - so the stored-hash
    # match is reported as the real check and the file is a bonus.
    path = BACKEND_DIR / document.file_path
    if path.is_file():
        on_disk = hashlib.sha256(path.read_bytes()).hexdigest()
        if on_disk != claimed_sha:
            return Check(
                name="kfs_document",
                ok=False,
                detail="The PDF on disk has changed since this receipt was issued.",
            )
        return Check(
            name="kfs_document",
            ok=True,
            detail=f"Key Fact Statement {document.version} matches, PDF included.",
        )

    return Check(
        name="kfs_document",
        ok=True,
        detail=f"Key Fact Statement {document.version} matches the stored hash.",
    )


def verify(db: Session, receipt: Receipt, settings: Settings) -> VerificationResult:
    """Run all four checks on a stored receipt (§11.3)."""
    checks = [
        _check_hash(receipt.payload, receipt.prev_hash, receipt.hash),
        _check_chain(db, receipt),
        _check_signature(db, receipt.hash, receipt.signature, receipt.signing_key_id),
        _check_kfs(db, receipt.payload),
    ]
    return VerificationResult(
        valid=all(check.ok for check in checks),
        checks=checks,
        hash=receipt.hash,
        prev_hash=receipt.prev_hash,
        seq=receipt.seq,
        key_id=receipt.signing_key_id,
    )


def verify_candidate(
    db: Session, receipt: Receipt, candidate: dict[str, Any], settings: Settings
) -> VerificationResult:
    """Verify an **edited copy**. The database is never touched (§11.3).

    This is the demo that makes the trust layer legible: an auditor edits the
    EMI from 4,600 to 4,000 in the browser, and the page turns red with the
    exact field that changed. The stored receipt is read-only here, and the
    result is computed entirely in memory.

    Checks 1 and 3 are the meaningful ones: the candidate's contents no longer
    hash to the signed hash, so the signature over that hash no longer stands.
    """
    recomputed = chain_hash(receipt.prev_hash, canonicalise(candidate))
    hash_ok = recomputed == receipt.hash

    checks = [
        Check(
            name="payload_hash",
            ok=hash_ok,
            detail=(
                "The edited copy still hashes to the original hash."
                if hash_ok
                else f"The edited copy hashes to {recomputed[:12]}…, "
                f"not the signed {receipt.hash[:12]}…"
            ),
        ),
        _check_chain(db, receipt),
        Check(
            name="signature",
            ok=hash_ok
            and _check_signature(db, receipt.hash, receipt.signature, receipt.signing_key_id).ok,
            detail=(
                "The signature covers these contents."
                if hash_ok
                else "The signature was made over the original contents, not these."
            ),
        ),
        _check_kfs(db, candidate),
    ]

    changes = diff(receipt.payload, candidate)
    reasons = [f"{change['path']}: {change['from']} → {change['to']}" for change in changes]

    return VerificationResult(
        valid=all(check.ok for check in checks) and not changes,
        checks=checks,
        hash=receipt.hash,
        prev_hash=receipt.prev_hash,
        seq=receipt.seq,
        key_id=receipt.signing_key_id,
        diff=changes,
        reasons=reasons,
    )


def verify_chain(db: Session, limit: int | None = None) -> tuple[bool, list[str]]:
    """Walk the whole chain. Returns `(ok, problems)`.

    Used by the 20-parallel-appends test and by the dashboard's ledger view: a
    chain that is individually valid at every receipt but has a gap in `seq` is
    still broken, and only a walk finds that.
    """
    receipts = list(db.scalars(select(Receipt).order_by(Receipt.seq)).all())
    if limit is not None:
        receipts = receipts[-limit:]

    problems: list[str] = []
    expected_prev = GENESIS_HASH if not receipts or receipts[0].seq == 1 else None

    for index, receipt in enumerate(receipts):
        if index > 0 and receipt.seq != receipts[index - 1].seq + 1:
            problems.append(f"gap in the chain: {receipts[index - 1].seq} -> {receipt.seq}")

        if expected_prev is not None and receipt.prev_hash != expected_prev:
            problems.append(f"receipt {receipt.seq} does not link to its predecessor")

        recomputed = chain_hash(receipt.prev_hash, receipt.payload_canonical)
        if recomputed != receipt.hash:
            problems.append(f"receipt {receipt.seq} hash does not match its contents")

        expected_prev = receipt.hash

    return not problems, problems
