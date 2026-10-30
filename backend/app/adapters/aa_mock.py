"""Account Aggregator: bank statement data (build plan §9 PREFILL).

This adapter produces the two numbers the suitability decision rests on - the
customer's average monthly income and the EMI they already pay - so it is the
one whose provenance matters most. On a real loan these come from a consented,
digitally signed bank statement, which is why the figures can be called
*verified* rather than *declared*.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterResult, MockLatency, PrefillAdapter, PrefillRow
from app.db.models.persona import AaStatement


class MockAccountAggregator(PrefillAdapter):
    """Averages the persona's six seeded months of credits."""

    source = "Account Aggregator"

    def __init__(self, db: Session) -> None:
        self._db = db

    async def fetch(self, persona_id: str) -> AdapterResult:
        statements = self._db.scalars(
            select(AaStatement)
            .where(AaStatement.persona_id == persona_id)
            .order_by(AaStatement.month)
        ).all()

        latency = await MockLatency.wait()
        result = AdapterResult(source=self.source, latency_ms=latency)
        if not statements:
            return result

        # Mean of total credits, which is how a lender reads a statement for a
        # self-employed borrower with no salary slip - the whole reason this
        # customer struggles to borrow at a fair rate in the first place.
        average = sum(float(s.total_credits) for s in statements) / len(statements)
        income = round(average)
        existing_emi = round(float(statements[-1].existing_emi))
        bounces = sum(s.bounce_count for s in statements)

        result.rows.append(PrefillRow("Average monthly income", f"₹{income:,}", self.source))
        if existing_emi:
            result.rows.append(PrefillRow("Existing EMI", f"₹{existing_emi:,}", self.source))

        result.data.update(
            {
                "monthly_income": income,
                "existing_emi": existing_emi,
                "bounce_count": bounces,
                "months_analysed": len(statements),
            }
        )
        return result


class RealAccountAggregator(PrefillAdapter):
    """Production Account Aggregator, not implemented.

    The RBI's AA framework routes data through a licensed Account Aggregator
    (Finvu, OneMoney, Setu and others). The flow is: register as a Financial
    Information User, raise a consent request naming purpose, data range and
    validity, let the customer approve it in the AA's own app, then fetch the
    signed Financial Information from the FIP. The consent artefact is itself
    evidence and would be stored in `consents.evidence`.
    """

    source = "Account Aggregator"

    async def fetch(self, persona_id: str) -> AdapterResult:
        raise NotImplementedError(
            "AA data requires a licensed Account Aggregator and an FIU "
            "registration. See the class docstring."
        )
