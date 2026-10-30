"""CKYC: the central KYC registry record (build plan §9 PREFILL)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterResult, MockLatency, PrefillAdapter, PrefillRow
from app.db.models.persona import CkycRecord


class MockCkyc(PrefillAdapter):
    """Returns the persona's seeded, masked CKYC record."""

    source = "CKYC"

    def __init__(self, db: Session) -> None:
        self._db = db

    async def fetch(self, persona_id: str) -> AdapterResult:
        record = self._db.scalar(select(CkycRecord).where(CkycRecord.persona_id == persona_id))

        latency = await MockLatency.wait()
        result = AdapterResult(source=self.source, latency_ms=latency)
        if record is None:
            return result

        result.rows.append(PrefillRow("KYC status", record.kyc_status.title(), self.source))
        result.data["ckyc_masked"] = record.ckyc_number_masked
        result.data["kyc_status"] = record.kyc_status
        return result


class RealCkyc(PrefillAdapter):
    """Production CKYC, not implemented.

    CERSAI's CKYC Registry is reachable only by regulated entities - banks,
    NBFCs, insurers - over a mutually authenticated connection, searching by
    CKYC identifier or by PAN with the customer's authorisation. A fintech
    accesses it through its lending partner, never directly, so in production
    this adapter would call the partner's API rather than CERSAI.
    """

    source = "CKYC"

    async def fetch(self, persona_id: str) -> AdapterResult:
        raise NotImplementedError(
            "CKYC is accessible only to regulated entities via CERSAI. See the class docstring."
        )
