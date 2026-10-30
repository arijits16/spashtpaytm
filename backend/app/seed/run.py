"""Idempotent seed loader (`make seed`, build plan phase 2).

Run it as often as you like: every row is upserted by its natural key, so a
second run updates in place and never duplicates. That matters because the demo
is reset and re-seeded between rehearsals, and a seeder that only works on an
empty database is a seeder that fails at the worst time.

What it loads, in dependency order:

  1. personas + their DigiLocker / CKYC / Account Aggregator mock records;
  2. lenders;
  3. the three KFS PDFs (regenerated, hashed) and their clauses;
  4. loan offers, **priced by `loan_math`** rather than by the seed file;
  5. the teach-back question bank;
  6. the ledger head row.

The derived loan numbers are deliberately not in `offers.json`. If they were,
someone would eventually edit one by hand and the database would disagree with
the arithmetic that a receipt is verified against.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.catalog import KfsClause, KfsDocument, Lender, LoanOffer, TeachbackQuestion
from app.db.models.persona import AaStatement, CkycRecord, DigilockerRecord, Persona
from app.db.models.trust import GENESIS_HASH, LedgerHead
from app.db.session import SessionLocal

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _load(name: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def _upsert(session: Session, model: type, key: dict[str, Any], values: dict[str, Any]) -> Any:
    """Fetch-or-create by `key`, then overwrite `values`.

    A hand-rolled upsert rather than `ON CONFLICT` because the seed files are
    small and this keeps the ORM objects in the session, which the callers need
    in order to link children to parents.
    """
    stmt = select(model).filter_by(**key)
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        row = model(**key, **values)
        session.add(row)
    else:
        for field, value in values.items():
            setattr(row, field, value)
    session.flush()
    return row


# --- 1. personas -------------------------------------------------------------


def seed_personas(session: Session) -> int:
    """Personas and the three mock data sources the prefill adapters read.

    The child records are replaced rather than upserted: they have no stable
    natural key (a persona can have two address proofs), and deleting a handful
    of synthetic rows is simpler to reason about than matching on content.
    """
    data = _load("personas.json")

    for entry in data["personas"]:
        persona = _upsert(
            session,
            Persona,
            {"id": entry["id"]},
            {
                "full_name": entry["full_name"],
                "display_name_masked": entry["display_name_masked"],
                "name_local": entry["name_local"],
                "gender": entry["gender"],
                "age": entry["age"],
                "dob": date.fromisoformat(entry["dob"]),
                "city": entry["city"],
                "locality": entry["locality"],
                "occupation": entry["occupation"],
                "business_name": entry.get("business_name"),
                "language": entry["language"],
                "mobile_masked": entry["mobile_masked"],
                "consent_callbacks": entry["consent_callbacks"],
                "dnd": entry["dnd"],
            },
        )

        session.execute(delete(DigilockerRecord).where(DigilockerRecord.persona_id == persona.id))
        for doc in entry.get("digilocker", []):
            session.add(
                DigilockerRecord(
                    persona_id=persona.id,
                    doc_type=doc["doc_type"],
                    data=doc["data"],
                    issuer=doc["issuer"],
                )
            )

        session.execute(delete(CkycRecord).where(CkycRecord.persona_id == persona.id))
        ckyc = entry["ckyc"]
        session.add(
            CkycRecord(
                persona_id=persona.id,
                ckyc_number_masked=ckyc["ckyc_number_masked"],
                kyc_status=ckyc["kyc_status"],
                last_updated=date.fromisoformat(ckyc["last_updated"]),
                data=ckyc["data"],
            )
        )

        session.execute(delete(AaStatement).where(AaStatement.persona_id == persona.id))
        aa = entry["aa"]
        for month in aa["months"]:
            session.add(
                AaStatement(
                    persona_id=persona.id,
                    fip_name=aa["fip_name"],
                    account_masked=aa["account_masked"],
                    month=date.fromisoformat(month["month"]),
                    total_credits=month["credits"],
                    total_debits=month["debits"],
                    avg_balance=month["avg_balance"],
                    bounce_count=month["bounces"],
                    existing_emi=aa["existing_emi"],
                )
            )

    session.flush()
    return len(data["personas"])


# --- 2-4. lenders, KFS documents and offers ---------------------------------


def seed_catalog(session: Session) -> tuple[int, int]:
    """Lenders, KFS documents (with freshly generated PDFs) and priced offers.

    Importing the generator here rather than at module scope keeps `reportlab`
    off the import path of the running API: the backend never needs it, only
    this script does.
    """
    from scripts.generate_kfs_pdf import generate_all

    catalog = _load("offers.json")

    for entry in catalog["lenders"]:
        _upsert(
            session,
            Lender,
            {"id": entry["id"]},
            {
                "name": entry["name"],
                "type": entry["type"],
                "reg_no_sample": entry["reg_no_sample"],
                "grievance_contact_sample": entry["grievance_contact_sample"],
            },
        )

    # Regenerating the PDFs on every seed is what keeps the stored SHA-256
    # truthful: the hash always describes the file that is actually on disk.
    documents = {doc["offer_id"]: doc for doc in generate_all()}
    offers_by_id = {entry["id"]: entry for entry in catalog["offers"]}

    for offer_id, doc in documents.items():
        offer = offers_by_id[offer_id]

        kfs = _upsert(
            session,
            KfsDocument,
            {"offer_id": offer_id, "version": doc["version"]},
            {
                "lender_id": doc["lender_id"],
                "file_path": doc["file_path"],
                "file_sha256": doc["file_sha256"],
                "facts": doc["facts"],
                "source": "seed",
                "status": "active",
                "verified_by": "seed (synthetic sample)",
                "verified_at": datetime.now().astimezone(),
            },
        )

        # Clauses are replaced wholesale: their text is regenerated from the
        # templates each run, so matching on key would leave stale rows behind
        # if a clause were ever renamed.
        session.execute(delete(KfsClause).where(KfsClause.kfs_document_id == kfs.id))
        for clause in doc["clauses"]:
            session.add(
                KfsClause(
                    kfs_document_id=kfs.id,
                    clause_key=clause["clause_key"],
                    title=clause["title"],
                    text_en=clause["text_en"],
                )
            )

        facts = doc["facts"]
        _upsert(
            session,
            LoanOffer,
            {"id": offer_id},
            {
                "lender_id": offer["lender_id"],
                "product": "personal_loan",
                "principal": facts["principal"],
                "tenure_months": facts["tenure_months"],
                "rate_pa": facts["rate_pa"],
                "rate_type": "reducing",
                "processing_fee": facts["processing_fee"],
                "gst_on_fee": facts["gst"],
                "emi": facts["emi"],
                "total_repay": facts["total_repay"],
                "total_interest": facts["total_interest"],
                "apr": facts["apr"],
                "late_fee": facts["late_fee"],
                "foreclosure_pct": facts["foreclosure_pct"],
                "cooling_off_days": facts["cooling_off_days"],
                "insurance_optional": True,
                "insurance_premium": facts["insurance_premium"],
                "kfs_document_id": kfs.id,
                "active": True,
            },
        )

    session.flush()
    return len(catalog["lenders"]), len(documents)


# --- 5. teach-back bank ------------------------------------------------------


def seed_teachback(session: Session) -> int:
    data = _load("teachback.json")
    questions = [q for q in data["questions"] if "id" in q]

    for entry in questions:
        _upsert(
            session,
            TeachbackQuestion,
            {"id": entry["id"]},
            {
                "kfs_fact_key": entry["kfs_fact_key"],
                "sort_order": entry["sort_order"],
                "prompt": entry["prompt"],
                "options": entry["options"],
                "reexplain": entry["reexplain"],
                "rubric": entry["rubric"],
                # The spare question is seeded inactive (§7.3).
                "active": entry.get("active", True),
            },
        )

    session.flush()
    return len(questions)


# --- 6. ledger head ---------------------------------------------------------


def ensure_ledger_head(session: Session) -> None:
    """Make sure the chain has a tip. The migration inserts it; this is the
    belt-and-braces path for a database restored from an older dump."""
    head = session.get(LedgerHead, 1)
    if head is None:
        session.add(LedgerHead(id=1, last_seq=0, last_hash=GENESIS_HASH))
        session.flush()


def run() -> dict[str, int]:
    """Load everything in one transaction. Returns a count per group."""
    sys.path.insert(0, str(BACKEND_DIR))

    with SessionLocal() as session:
        counts = {"personas": seed_personas(session)}
        lenders, documents = seed_catalog(session)
        counts["lenders"] = lenders
        counts["kfs_documents"] = documents
        counts["offers"] = documents
        counts["teachback_questions"] = seed_teachback(session)
        ensure_ledger_head(session)
        session.commit()
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for group, count in run().items():
        print(f"  {group:22} {count}")
    print("==> seed complete (idempotent: safe to run again)")
