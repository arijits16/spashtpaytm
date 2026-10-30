"""DigiLocker: identity documents (build plan §9 PREFILL)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterResult, MockLatency, PrefillAdapter, PrefillRow
from app.db.models.persona import DigilockerRecord


class MockDigiLocker(PrefillAdapter):
    """Returns the persona's seeded Aadhaar, PAN and address proof.

    The session is passed in rather than opened here: the adapters run inside
    the turn's transaction, and a nested session would read a different snapshot
    from the engine that is about to store the result.
    """

    source = "DigiLocker"

    def __init__(self, db: Session) -> None:
        self._db = db

    async def fetch(self, persona_id: str) -> AdapterResult:
        records = self._db.scalars(
            select(DigilockerRecord).where(DigilockerRecord.persona_id == persona_id)
        ).all()

        latency = await MockLatency.wait()
        result = AdapterResult(source=self.source, latency_ms=latency)

        for record in records:
            payload = record.data or {}
            if record.doc_type == "aadhaar":
                masked = payload.get("number_masked", "")
                result.rows.append(PrefillRow("Aadhaar", masked, self.source))
                result.data["aadhaar_masked"] = masked
                # The name and date of birth come from the Aadhaar record
                # because that is the authoritative one of the three.
                result.data["full_name"] = payload.get("name")
                result.data["dob"] = payload.get("dob")
                if payload.get("name"):
                    result.rows.append(PrefillRow("Name", payload["name"], self.source))
            elif record.doc_type == "pan":
                masked = payload.get("number_masked", "")
                result.rows.append(PrefillRow("PAN", masked, self.source))
                result.data["pan_masked"] = masked
            elif record.doc_type == "address_proof":
                address = payload.get("address", "")
                result.rows.append(PrefillRow("Address", address, self.source))
                result.data["address"] = address
                # Pre-filled as the shop address, which the customer confirms
                # or edits at CONFIRM_DETAILS - never silently accepted.
                result.data["shop_address"] = address

        return result


class RealDigiLocker(PrefillAdapter):
    """Production DigiLocker, not implemented.

    A real integration needs the customer to authenticate at
    `digilocker.meripehchaan.gov.in` through an OAuth2 consent flow, after which
    the partner application exchanges the code for a token and pulls issued
    documents from the Pull Document API. Access requires a registered
    requester organisation and a signed agreement with NeGD; the consent
    artefact must be retained as evidence, which is what `consents` is for.
    """

    source = "DigiLocker"

    async def fetch(self, persona_id: str) -> AdapterResult:
        raise NotImplementedError(
            "Real DigiLocker access requires a registered requester "
            "organisation and the OAuth2 consent flow. See the class docstring."
        )
