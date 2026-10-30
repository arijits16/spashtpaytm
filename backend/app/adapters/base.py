"""Prefill adapter interfaces (build plan §9 PREFILL).

Four sources fill the loan form: DigiLocker for identity documents, CKYC for the
registry record, an Account Aggregator for bank statements, and UPI AutoPay for
the mandate. In this demo all four are mocks that read seeded persona data.

Each adapter has a `Mock*` and a `Real*` class. The `Real*` classes raise
`NotImplementedError` with a docstring naming what production would actually
need - a licence, a partner contract, a certified AA. Writing them down as code
rather than as a TODO keeps the demo honest: the shape of the real integration
is visible, and nobody can mistake the mock for a working one.
"""

from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PrefillRow:
    """One fetched value, tagged with the source that produced it."""

    label: str
    value: str
    source: str


@dataclass
class AdapterResult:
    """What one adapter returned.

    `rows` is what the customer sees; `data` is the machine-readable form the
    engine stores in the context. They are separate because the screen wants
    "Aadhaar · XXXX XXXX 4821" and the engine wants `aadhaar_masked`.
    """

    source: str
    rows: list[PrefillRow] = field(default_factory=list)
    data: dict[str, object] = field(default_factory=dict)
    latency_ms: int = 0


class PrefillAdapter(ABC):
    """One source of pre-fillable customer data."""

    #: What the UI shows as the provenance tag (§8.4 `PrefillRow.source`).
    source: str

    @abstractmethod
    async def fetch(self, persona_id: str) -> AdapterResult:
        """Fetch this source's data for a persona."""


class MockLatency:
    """Shared 0.8-1.5 s mock delay (§9 PREFILL).

    The delay is not decoration. The adapters run concurrently, and a real
    DigiLocker call takes about a second, so without it the staggered fade-in
    that tells the customer *where each value came from* would flash past
    unread - and that reassurance is the point of the screen.
    """

    LOW_SECONDS = 0.8
    HIGH_SECONDS = 1.5

    @classmethod
    async def wait(cls) -> int:
        """Sleep a plausible amount. Returns the elapsed milliseconds."""
        seconds = random.uniform(cls.LOW_SECONDS, cls.HIGH_SECONDS)  # noqa: S311
        await asyncio.sleep(seconds)
        return int(seconds * 1000)
