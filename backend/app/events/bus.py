"""The in-process event bus behind the dashboard's live feed (plan §12, phase 9).

When a journey completes on the phone, the laptop has to show it within two
seconds without anyone refreshing. This is how: the routes publish, and each
connected dashboard holds a subscription that its SSE stream drains.

**One process, one bus.** A laptop running one uvicorn worker needs no Redis,
and adding one would be infrastructure to debug on stage. In production this
becomes Redis pub/sub, which is recorded as a residual risk in `docs/SECURITY.md`.

**Slow subscribers are dropped, not waited for.** Each queue is bounded, and a
publish to a full queue discards the oldest event rather than blocking. A
dashboard left open on a sleeping laptop must never be able to stall the turn a
customer is taking - the feed is a convenience and the journey is the product.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# The event names of §8.2. Named constants so a publisher and the website's
# `switch` cannot drift apart silently.
JOURNEY_UPDATED = "journey.updated"
RECEIPT_CREATED = "receipt.created"
RESCUE_CREATED = "rescue.created"
GUARD_BLOCKED = "guard.blocked"
DEMO_RESET = "demo.reset"

# Deep enough to absorb a burst of turns, shallow enough that a stalled
# dashboard cannot hold much memory.
QUEUE_SIZE = 64

# Sent every 20 s so a proxy or a phone's radio does not close an idle stream.
HEARTBEAT_SECONDS = 20


@dataclass(frozen=True, slots=True)
class Event:
    """One thing that happened.

    `data` is for a dashboard, so it carries **no** personal detail: a persona
    id, a step, a masked name. Never a transcript, never an unmasked field - an
    SSE stream is one more place data can leak to, and the same rules apply as
    to logs (§13.8).
    """

    name: str
    data: dict[str, Any]
    at: float = field(default_factory=time.time)

    def to_sse(self, event_id: int) -> str:
        """Render as a Server-Sent Events frame."""
        payload = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"))
        return f"id: {event_id}\nevent: {self.name}\ndata: {payload}\n\n"


class EventBus:
    """Fan-out to every connected dashboard."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._sequence = 0

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, name: str, data: dict[str, Any]) -> None:
        """Publish an event. Never blocks and never raises.

        Called from request handlers, including synchronous ones, so it must be
        safe to call when there is no running loop and when nobody is listening.
        A dashboard notification is not worth a 500 on a customer's turn.
        """
        if not self._subscribers:
            return

        event = Event(name=name, data=data)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop the oldest and keep the newest: a dashboard that fell
                # behind wants the current state, not a backlog.
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)

    async def subscribe(self) -> AsyncIterator[str]:
        """Yield SSE frames until the client disconnects.

        An initial comment frame is sent immediately, so the browser's
        `EventSource` resolves its connection rather than sitting in `CONNECTING`
        until the first real event - which could be minutes.
        """
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(queue)
        log.info("dashboard subscribed", extra={"subscribers": len(self._subscribers)})

        try:
            yield ": connected\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    # A comment, not an event: it keeps the connection warm
                    # without the client having to filter it out.
                    yield ": heartbeat\n\n"
                    continue

                self._sequence += 1
                yield event.to_sse(self._sequence)

        finally:
            self._subscribers.discard(queue)
            log.info("dashboard unsubscribed", extra={"subscribers": len(self._subscribers)})

    def reset(self) -> None:
        """Drop every subscriber. Tests only."""
        self._subscribers.clear()
        self._sequence = 0


bus = EventBus()


def publish_journey_updated(
    journey_id: Any, *, step: str, status: str, persona_id: str | None, language: str
) -> None:
    """A journey moved. The dashboard's live table rows come from this."""
    bus.publish(
        JOURNEY_UPDATED,
        {
            "journeyId": str(journey_id),
            "step": step,
            "status": status,
            "personaId": persona_id,
            "language": language,
        },
    )


def publish_receipt_created(*, receipt_no: str, seq: int, lender: str, journey_id: Any) -> None:
    """A receipt was appended. This is the 2-second claim of phase 9."""
    bus.publish(
        RECEIPT_CREATED,
        {
            "receiptNo": receipt_no,
            "seq": seq,
            "lender": lender,
            "journeyId": str(journey_id),
        },
    )


def publish_guard_blocked(*, journey_id: Any, blocked: list[float], kind: str) -> None:
    """The Number Guard rejected generated text (§10.5). Counted as a KPI."""
    bus.publish(
        GUARD_BLOCKED,
        {"journeyId": str(journey_id), "blocked": blocked, "kind": kind},
    )


def publish_rescue_created(*, task_id: Any, journey_id: Any, step: str, reason: str) -> None:
    """The rescue agent created a task (phase 10)."""
    bus.publish(
        RESCUE_CREATED,
        {
            "taskId": str(task_id),
            "journeyId": str(journey_id),
            "step": step,
            "reason": reason,
        },
    )
