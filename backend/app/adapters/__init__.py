"""Prefill adapters: DigiLocker, CKYC, Account Aggregator, UPI AutoPay.

`run_prefill` is the only entry point the engine uses.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session

from app.adapters.aa_mock import MockAccountAggregator, RealAccountAggregator
from app.adapters.base import AdapterResult, PrefillAdapter, PrefillRow
from app.adapters.ckyc_mock import MockCkyc, RealCkyc
from app.adapters.digilocker_mock import MockDigiLocker, RealDigiLocker
from app.adapters.upi_autopay_mock import MockUpiAutopay, RealUpiAutopay

log = logging.getLogger(__name__)

__all__ = [
    "AdapterResult",
    "MockAccountAggregator",
    "MockCkyc",
    "MockDigiLocker",
    "MockUpiAutopay",
    "PrefillAdapter",
    "PrefillRow",
    "RealAccountAggregator",
    "RealCkyc",
    "RealDigiLocker",
    "RealUpiAutopay",
    "run_prefill",
]


async def run_prefill(
    db: Session,
    persona_id: str,
    *,
    include_identity: bool,
    include_financial: bool,
) -> list[AdapterResult]:
    """Run the consented adapters concurrently (§9 PREFILL).

    @param include_identity   The customer granted `fetch_digilocker`.
    @param include_financial  The customer granted `fetch_account_aggregator`.

    Which adapters run is decided by what was consented to, one purpose at a
    time: granting DigiLocker but not bank access must fetch documents and not
    statements. Concurrency is what keeps the whole screen inside the ~1.5 s
    budget instead of four sequential seconds, and `gather` is safe here because
    the mocks only read.

    An adapter that fails is logged and skipped. A missing CKYC row must not
    cost the customer their loan application.
    """
    adapters: list[PrefillAdapter] = []
    if include_identity:
        adapters.extend([MockDigiLocker(db), MockCkyc(db)])
    if include_financial:
        adapters.extend([MockAccountAggregator(db), MockUpiAutopay(db)])

    if not adapters:
        return []

    outcomes = await asyncio.gather(
        *(adapter.fetch(persona_id) for adapter in adapters),
        return_exceptions=True,
    )

    results: list[AdapterResult] = []
    for adapter, outcome in zip(adapters, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            log.warning(
                "prefill adapter failed",
                extra={"source": adapter.source, "error_type": type(outcome).__name__},
            )
            continue
        results.append(outcome)
    return results
