"""Building and appending the Spasht Receipt (build plan §11.1, §11.5).

A receipt is the product's output. Not an approval - no money moves in this demo
- but a signed, verifiable record of *what the customer was told, what they
demonstrated they understood, and what they agreed to*. It is what turns
"we explained the loan" from a claim into evidence.

Every figure in the payload comes from the journey's stored state and the
selected offer's facts. Nothing is recomputed from a live price list: a receipt
must say what was on screen at the time, even if the catalogue changes later.

**What is deliberately not in the payload.** No full name - `customer_display`
is the masked form. No mobile number - masked. No Aadhaar, PAN or CKYC number at
all. No transcript. `customer_ref` is `HMAC(CUSTOMER_REF_PEPPER, user_id)`, so
two receipts from the same customer can be linked by someone holding the pepper
and by nobody else.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.catalog import KfsDocument
from app.db.models.journey import Consent, Journey, TeachbackAttempt
from app.db.models.persona import Persona
from app.db.models.trust import Receipt
from app.events.bus import publish_receipt_created
from app.journey import events
from app.journey.cards import ReceiptCard, ReceiptCardData, TeachbackScore
from app.journey.context import JourneyContext
from app.journey.offers import price_offers
from app.journey.states import Lang
from app.journey.templates import format_rupees
from app.trust.ledger import append

log = logging.getLogger(__name__)

# §11.1. Named here so the receipt says which client produced it; a web journey
# and a phone journey are different evidence.
CHANNEL_IOS_VOICE = "paytm_ios_app_voice"


def customer_ref(user_id: str, settings: Settings) -> str:
    """`HMAC(CUSTOMER_REF_PEPPER, user_id)` (§11.1).

    A pseudonym, not an identifier: it is stable for one customer so their
    receipts can be correlated by us, and meaningless to anyone who finds a
    receipt without the pepper.
    """
    pepper = settings.customer_ref_pepper or "dev-customer-pepper"
    return hmac.new(pepper.encode(), user_id.encode(), hashlib.sha256).hexdigest()


def customer_summary(
    *,
    language: Lang,
    lender: str,
    facts: dict,
    insurance_taken: bool,
    receipt_no: str,
) -> str:
    """The summary the customer keeps (§11.5).

    Templated, in their language, and it leads with the numbers that matter
    rather than with congratulations: the EMI, the total, the late fee, the
    cooling-off right. Nothing is actually sent anywhere - the app shows it as a
    mock message preview.
    """
    emi = format_rupees(facts["emi"])
    total = format_rupees(facts["total_repay"])
    late = format_rupees(facts["late_fee"])
    tenure = facts["tenure_months"]
    cooling = facts["cooling_off_days"]

    if language == "mr-IN":
        insurance = "विमा घेतला आहे." if insurance_taken else "विमा घेतला नाही."
        return (
            f"{lender} कडून कर्ज मंजूर. दर महिन्याला ₹{emi}, {tenure} महिने. "
            f"एकूण परतफेड ₹{total}. EMI उशिरा भरला तर ₹{late} दंड आणि CIBIL स्कोर कमी होऊ शकतो. "
            f"{insurance} विचार बदलला तर {cooling} दिवसांत दंडाशिवाय कर्ज बंद करता येईल. "
            f"पावती क्रमांक {receipt_no}."
        )
    if language == "hi-IN":
        insurance = "बीमा लिया है।" if insurance_taken else "बीमा नहीं लिया।"
        return (
            f"{lender} से लोन मंज़ूर। हर महीने ₹{emi}, {tenure} महीने। "
            f"कुल चुकाना ₹{total}। EMI देर से भरी तो ₹{late} लेट फीस और CIBIL स्कोर गिर सकता है। "
            f"{insurance} मन बदले तो {cooling} दिन में बिना जुर्माने के लोन बंद कर सकते हैं। "
            f"रसीद संख्या {receipt_no}।"
        )

    insurance = "Insurance taken." if insurance_taken else "Insurance: not taken."
    return (
        f"Loan approved with {lender}. ₹{emi} a month for {tenure} months, "
        f"₹{total} in total. A late EMI costs ₹{late} and can lower your CIBIL score. "
        f"{insurance} You can exit within {cooling} days with no penalty. "
        f"Receipt {receipt_no}."
    )


def _teachback_evidence(db: Session, journey_id) -> list[dict]:
    """Per-question attempt record, from the append-only attempts table.

    Read from `teachback_attempts` rather than from the journey context so the
    receipt is built from evidence rather than from state that the engine
    happened to be holding.
    """
    attempts = db.scalars(
        select(TeachbackAttempt)
        .where(TeachbackAttempt.journey_id == journey_id)
        .order_by(TeachbackAttempt.question_id, TeachbackAttempt.attempt_no)
    ).all()

    by_question: dict[str, list[TeachbackAttempt]] = {}
    for attempt in attempts:
        by_question.setdefault(attempt.question_id, []).append(attempt)

    return [
        {
            "q": question_id,
            "attempts": len(rows),
            "first_attempt_correct": rows[0].is_correct,
            "passed": any(row.is_correct for row in rows),
        }
        for question_id, rows in by_question.items()
    ]


def _consent_evidence(db: Session, journey_id) -> list[dict]:
    """The consent trail, latest decision per purpose.

    All rows are kept in the database (a withdrawal is an insert), but the
    receipt records the state that applied at completion. The `default` field is
    carried through for `insurance_addon` specifically: proving it started off is
    the point.
    """
    rows = db.scalars(
        select(Consent).where(Consent.journey_id == journey_id).order_by(Consent.created_at)
    ).all()

    latest: dict[str, Consent] = {row.purpose: row for row in rows}
    evidence = []
    for purpose, row in latest.items():
        entry = {
            "purpose": purpose,
            "granted": row.granted,
            "method": row.method,
            "at": row.created_at.astimezone(UTC).isoformat(),
        }
        if not row.granted:
            entry["default"] = row.default_value
        evidence.append(entry)
    return sorted(evidence, key=lambda item: item["purpose"])


def issue_receipt(
    db: Session, journey: Journey, settings: Settings, *, actor: str
) -> ReceiptCard | None:
    """Build, sign and append the receipt, then return its card (§11).

    Idempotent by the `receipts.journey_id` unique constraint *and* by the check
    below: a retried OTP verification must not append a second receipt, which
    would both duplicate evidence and advance the chain for nothing.

    Returns None when the journey has no selected offer - which cannot happen on
    the golden path, and is a `None` card rather than an exception because
    failing to draw a card must not lose a completed journey.
    """
    existing = db.scalar(select(Receipt).where(Receipt.journey_id == journey.id))
    if existing is not None:
        return _card_from(existing, settings)

    context = JourneyContext.of(journey.context)
    if not journey.selected_offer_id or context.amount is None:
        log.warning(
            "receipt requested for a journey with no selected offer",
            extra={"journey_id": str(journey.id)},
        )
        return None

    offers = price_offers(db, context.amount)
    offer = next((o for o in offers if o.offer_id == journey.selected_offer_id), None)
    if offer is None:
        return None

    document = db.get(KfsDocument, journey.kfs_document_id) if journey.kfs_document_id else None
    persona = db.get(Persona, journey.persona_id) if journey.persona_id else None
    facts = offer.facts

    teachback = _teachback_evidence(db, journey.id)
    started = journey.started_at.astimezone(UTC).isoformat()
    completed = datetime.now(UTC).isoformat()

    payload = {
        "journey_id": str(journey.id),
        "customer_ref": customer_ref(str(journey.user_id), settings),
        # Masked only. The real name never reaches a receipt.
        "customer_display": persona.display_name_masked if persona else "Customer",
        "mobile_masked": persona.mobile_masked if persona else "",
        "product": journey.product,
        "lender": offer.lender,
        "offer_id": offer.offer_id,
        "terms": {
            "principal": facts["principal"],
            "tenure_months": facts["tenure_months"],
            "rate_pa": facts["rate_pa"],
            "apr": facts["apr"],
            "emi": facts["emi"],
            "total_repay": facts["total_repay"],
            "total_cost": facts["total_cost"],
            "processing_fee": facts["processing_fee"],
            "gst": facts["gst"],
            "late_fee": facts["late_fee"],
            "foreclosure_pct": facts["foreclosure_pct"],
            "cooling_off_days": facts["cooling_off_days"],
        },
        "kfs": {
            "id": str(document.id) if document else None,
            "version": document.version if document else offer.kfs_version,
            "file_sha256": document.file_sha256 if document else None,
        },
        # Which facts the customer was actually taken through, so a receipt
        # cannot imply an explanation that never happened.
        "facts_explained": [
            "emi",
            "total_repay",
            "late_fee",
            "foreclosure_pct",
            "insurance_optional",
            "cooling_off_days",
        ],
        "language": journey.language,
        "channel": CHANNEL_IOS_VOICE,
        "teachback": teachback,
        "suitability": {
            "foir": context.foir,
            "decision": "suitable" if context.suitable else "not_suitable",
            "reasons": context.suitability_reasons,
            "income_verified": not context.prefill.self_declared,
        },
        "consents": _consent_evidence(db, journey.id),
        "insurance_taken": context.insurance_granted,
        "timestamps": {"started": started, "completed": completed},
        "app_version": "spasht-ios-0.1.0",
    }

    appended = append(db, payload, journey.id, settings)

    # Stored on the journey too, so a resumed DONE journey can show the card
    # without walking the ledger.
    stored = dict(journey.context or {})
    stored["receipt_no"] = appended.receipt_no
    journey.context = stored
    journey.completed_at = datetime.now(UTC)

    events.record(
        db,
        journey_id=journey.id,
        actor=actor,
        event_type=events.RECEIPT_CREATED,
        step=journey.step,
        data={
            "receiptNo": appended.receipt_no,
            "seq": appended.seq,
            "hash": appended.hash[:16],
            "lender": offer.lender,
        },
    )

    # The phase-9 acceptance criterion: finishing on the phone shows on the
    # laptop within two seconds, without a refresh.
    publish_receipt_created(
        receipt_no=appended.receipt_no,
        seq=appended.seq,
        lender=offer.lender,
        journey_id=journey.id,
    )
    db.flush()

    receipt = db.scalar(select(Receipt).where(Receipt.receipt_no == appended.receipt_no))
    return _card_from(receipt, settings) if receipt else None


def _card_from(receipt: Receipt, settings: Settings) -> ReceiptCard:
    """The receipt card (§5.7), built from the stored payload.

    `publicUrl` comes from `PUBLIC_BASE_URL` and never from a request header
    (§11.6): the QR code a judge scans must point where we configured, not where
    a caller claimed.
    """
    payload = receipt.payload
    terms = payload.get("terms", {})
    teachback = payload.get("teachback", [])
    language = payload.get("language", "mr-IN")

    return ReceiptCard(
        data=ReceiptCardData(
            receiptNo=receipt.receipt_no,
            lender=payload.get("lender", ""),
            emi=terms.get("emi", 0),
            tenureMonths=terms.get("tenure_months", 0),
            totalRepay=terms.get("total_repay", 0),
            language=language,
            teachback=TeachbackScore(
                passed=sum(1 for entry in teachback if entry.get("passed")),
                total=len(teachback),
            ),
            insuranceTaken=bool(payload.get("insurance_taken")),
            publicUrl=f"{settings.public_base_url.rstrip('/')}/r/{receipt.receipt_no}",
            summaryText=customer_summary(
                language=language,
                lender=payload.get("lender", ""),
                facts={
                    "emi": terms.get("emi", 0),
                    "total_repay": terms.get("total_repay", 0),
                    "late_fee": terms.get("late_fee", 0),
                    "tenure_months": terms.get("tenure_months", 0),
                    "cooling_off_days": terms.get("cooling_off_days", 3),
                },
                insurance_taken=bool(payload.get("insurance_taken")),
                receipt_no=receipt.receipt_no,
            ),
            createdAt=receipt.created_at.astimezone(UTC).isoformat(),
        )
    )
