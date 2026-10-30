"""Ranking and badging offers (build plan §9 OFFERS, §7.2).

One screen has to carry one idea: **the lowest interest rate is not the cheapest
loan**. Everything here serves that.

- Offers are sorted by **APR**, not by the advertised rate, so the genuinely
  cheapest option is first.
- `lowest_total_cost` (green) marks the offer that costs the customer least in
  rupees.
- `low_rate_high_fee` (amber) marks the trap: the lowest advertised rate whose
  all-in cost is beaten by another offer. It is a warning, not a recommendation.

A badge is only ever applied when it is true of the offers actually on screen -
nothing is hard-coded to `offer_b`, so the demo's punchline survives a change to
the seed data.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.catalog import KfsDocument, Lender, LoanOffer
from app.journey.loan_math import quote

Badge = str

BADGE_LOWEST_TOTAL_COST: Badge = "lowest_total_cost"
BADGE_LOW_RATE_HIGH_FEE: Badge = "low_rate_high_fee"


@dataclass(frozen=True, slots=True)
class PricedOffer:
    """One offer, priced for the amount the customer actually asked for.

    The seeded rows are priced at ₹50,000. Someone who asks for ₹75,000 must not
    be shown a ₹50,000 EMI, so every figure is recomputed from the offer's terms
    and the requested amount; only the terms (rate, fee, late fee) come from the
    database.
    """

    offer_id: str
    lender_id: str
    lender: str
    lender_type: str
    principal: int
    tenure_months: int
    rate_pa: float
    processing_fee: int
    gst: int
    emi: int
    total_repay: int
    total_interest: int
    total_cost: int
    apr: float
    late_fee: int
    foreclosure_pct: float
    cooling_off_days: int
    insurance_premium: int
    kfs_document_id: str | None
    kfs_version: str
    badges: tuple[Badge, ...] = ()

    def with_badges(self, badges: tuple[Badge, ...]) -> PricedOffer:
        """Frozen dataclass, so badging produces a new instance."""
        return replace(self, badges=badges)

    @property
    def facts(self) -> dict[str, object]:
        """The numeric facts the assistant may speak about this offer.

        This dict is the Number Guard's allow-list (§10.5) and the source of
        every `{PLACEHOLDER}` in a template or teach-back question. Scaled
        figures appear here rather than the seeded ones precisely because the
        guard must allow what is on screen, not what is in the catalogue.
        """
        return {
            "principal": self.principal,
            "tenure_months": self.tenure_months,
            "rate_pa": self.rate_pa,
            "processing_fee": self.processing_fee,
            "gst": self.gst,
            "net_disbursed": self.principal - self.processing_fee - self.gst,
            "emi": self.emi,
            "total_repay": self.total_repay,
            "total_interest": self.total_interest,
            "total_cost": self.total_cost,
            "apr": self.apr,
            "late_fee": self.late_fee,
            "foreclosure_pct": self.foreclosure_pct,
            "cooling_off_days": self.cooling_off_days,
            "insurance_optional": True,
            "insurance_premium": self.insurance_premium,
            "lender": self.lender,
            "kfs_version": self.kfs_version,
        }


def _scaled_fee(fee: int, principal: int, base_principal: int) -> int:
    """Scale a fee to the requested amount.

    A processing fee is a percentage of the loan in practice, so scaling it
    keeps the APR honest at a different amount. The GST is scaled with it rather
    than recomputed, which keeps the fee-to-GST ratio of the seeded offer
    (18%) without this module having to know the tax rate.
    """
    if base_principal <= 0 or principal == base_principal:
        return fee
    return round(fee * principal / base_principal)


def price_offers(db: Session, amount: int, tenure_months: int | None = None) -> list[PricedOffer]:
    """Price every active offer for `amount`, sorted by APR ascending."""
    rows = db.execute(
        select(LoanOffer, Lender, KfsDocument)
        .join(Lender, Lender.id == LoanOffer.lender_id)
        .outerjoin(KfsDocument, KfsDocument.id == LoanOffer.kfs_document_id)
        .where(LoanOffer.active.is_(True))
    ).all()

    priced: list[PricedOffer] = []
    for offer, lender, kfs in rows:
        tenure = tenure_months or offer.tenure_months
        fee = _scaled_fee(offer.processing_fee, amount, offer.principal)
        gst = _scaled_fee(offer.gst_on_fee, amount, offer.principal)

        figures = quote(amount, float(offer.rate_pa), tenure, fee, gst)

        priced.append(
            PricedOffer(
                offer_id=offer.id,
                lender_id=lender.id,
                lender=lender.name,
                lender_type=lender.type,
                principal=amount,
                tenure_months=tenure,
                rate_pa=float(offer.rate_pa),
                processing_fee=fee,
                gst=gst,
                emi=figures.emi,
                total_repay=figures.total_repay,
                total_interest=figures.total_interest,
                total_cost=figures.total_cost,
                apr=figures.apr,
                late_fee=offer.late_fee,
                foreclosure_pct=float(offer.foreclosure_pct),
                cooling_off_days=offer.cooling_off_days,
                insurance_premium=offer.insurance_premium,
                kfs_document_id=str(kfs.id) if kfs is not None else None,
                kfs_version=kfs.version if kfs is not None else "v1.0",
            )
        )

    return rank(priced)


def rank(offers: list[PricedOffer]) -> list[PricedOffer]:
    """Sort by APR and apply the badges (§7.2).

    Ties break on total cost and then on the offer id, so the order is stable
    across requests - a comparison screen that reshuffles between two taps
    destroys the customer's trust in it.
    """
    if not offers:
        return []

    ordered = sorted(offers, key=lambda o: (o.apr, o.total_cost, o.offer_id))

    cheapest = min(ordered, key=lambda o: (o.total_cost, o.apr))
    lowest_rate = min(ordered, key=lambda o: (o.rate_pa, o.total_cost))

    badged: list[PricedOffer] = []
    for offer in ordered:
        badges: list[Badge] = []
        if offer.offer_id == cheapest.offer_id:
            badges.append(BADGE_LOWEST_TOTAL_COST)
        # Only a warning when the headline rate is genuinely misleading: the
        # lowest-rate offer that something else beats on true cost. If the
        # lowest rate is also the cheapest, there is nothing to warn about.
        if (
            offer.offer_id == lowest_rate.offer_id
            and offer.offer_id != cheapest.offer_id
            and offer.total_cost > cheapest.total_cost
        ):
            badges.append(BADGE_LOW_RATE_HIGH_FEE)
        badged.append(offer.with_badges(tuple(badges)))

    return badged


def resolve_hint(offers: list[PricedOffer], hint: str | None) -> PricedOffer | None:
    """Turn an understanding hint ("cheapest", "index:0", "lender:X") into an offer.

    Spoken offer choice goes through here so `understand_rules` never needs to
    know what is on screen and the engine never needs to parse language.
    """
    if not offers or not hint:
        return None

    if hint == "cheapest":
        return min(offers, key=lambda o: (o.total_cost, o.apr))

    if hint.startswith("index:"):
        index = int(hint.removeprefix("index:"))
        return offers[index] if 0 <= index < len(offers) else None

    if hint.startswith("lender:"):
        name = hint.removeprefix("lender:").strip().lower()
        return next((o for o in offers if o.lender.lower() == name), None)

    return next((o for o in offers if o.offer_id == hint), None)


def lender_names(offers: list[PricedOffer]) -> tuple[str, ...]:
    """Lender names for `understand_rules.parse_offer_hint`."""
    return tuple(offer.lender for offer in offers)
