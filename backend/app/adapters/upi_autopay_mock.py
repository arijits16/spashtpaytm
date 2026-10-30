"""UPI AutoPay: the repayment mandate (build plan §9 PREFILL)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterResult, MockLatency, PrefillAdapter, PrefillRow
from app.db.models.persona import AaStatement, Persona


class MockUpiAutopay(PrefillAdapter):
    """Reports the account the EMI mandate would be set up on.

    Nothing is actually mandated: this is a concept demo and QR codes here never
    encode a `upi://` URL (plan rule 9). The row exists because seeing which
    account the money will leave is part of understanding the loan.
    """

    source = "UPI AutoPay"

    def __init__(self, db: Session) -> None:
        self._db = db

    async def fetch(self, persona_id: str) -> AdapterResult:
        persona = self._db.get(Persona, persona_id)
        statement = self._db.scalar(select(AaStatement).where(AaStatement.persona_id == persona_id))

        latency = await MockLatency.wait()
        result = AdapterResult(source=self.source, latency_ms=latency)
        if persona is None:
            return result

        result.rows.append(PrefillRow("Mobile", persona.mobile_masked, self.source))
        result.data["mobile"] = persona.mobile_masked

        if statement is not None:
            account = f"{statement.fip_name} · {statement.account_masked}"
            result.rows.append(PrefillRow("Repayment account", account, self.source))
            result.data["repayment_account"] = account

        return result


class RealUpiAutopay(PrefillAdapter):
    """Production UPI AutoPay, not implemented.

    A recurring e-mandate is created through a PSP on the NPCI UPI rails: the
    lender's PSP raises a mandate request, the customer approves it once in
    their UPI app with their PIN, and each instalment is then debited on the due
    date with a pre-debit notification. It needs a merchant/biller registration
    and a sponsor bank, neither of which a prototype has.
    """

    source = "UPI AutoPay"

    async def fetch(self, persona_id: str) -> AdapterResult:
        raise NotImplementedError(
            "UPI AutoPay mandates need a PSP integration and a sponsor bank. "
            "See the class docstring."
        )
