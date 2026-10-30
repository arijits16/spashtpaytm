"""Fulfilling an engine `GenerationRequest` (build plan §10.3, §10.5).

The engine has already produced a correct, seeded message. This replaces it with
a better-phrased or better-targeted one **only if** the model is available and
the Number Guard approves the result.

Three independent reasons nothing can go wrong here, which is why it is safe to
run on a live turn:

1. The seeded text is already on the response. This only ever overwrites it.
2. The Number Guard (§10.5) rejects any text containing a figure that is not a
   fact of the offer on screen, and its fallback *is* the seeded text.
3. Any exception leaves the seeded text in place.

A blocked generation is audited as `guard.blocked` and counted on the dashboard
(§12), because a guard that never fires should prompt the question of whether it
works - and the operator should be able to see that it does.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.ai.number_guard import GuardVerdict
from app.ai.reexplain import answer_kfs_question, reexplain
from app.ai.sarvam_client import demo_mode_active
from app.config import Settings
from app.db.models.journey import Journey
from app.events.bus import publish_guard_blocked
from app.journey import events
from app.journey.engine import EngineResult, GenerationRequest
from app.journey.responses import TurnResponse

log = logging.getLogger(__name__)


async def polish(
    db: Session,
    journey: Journey,
    result: EngineResult,
    response: TurnResponse,
    settings: Settings,
    *,
    actor: str,
) -> TurnResponse:
    """Improve one assistant message, if we can. Returns the response to send.

    Always returns a usable response: on any failure the one passed in comes
    straight back out.
    """
    request = result.generation
    if request is None or demo_mode_active(settings):
        return response

    def on_block(verdict: GuardVerdict) -> None:
        publish_guard_blocked(
            journey_id=journey.id,
            blocked=verdict.blocked_numbers,
            kind=request.kind,
        )
        events.record(
            db,
            journey_id=journey.id,
            actor="system",
            event_type=events.GUARD_BLOCKED,
            step=journey.step,
            data={
                "kind": request.kind,
                "blockedNumbers": verdict.blocked_numbers,
                "reason": verdict.reason,
            },
        )

    try:
        generated = await _generate(db, journey, request, settings, on_block)
    except Exception:
        log.exception("text polishing failed; the seeded message stands")
        return response

    if generated is None or not generated.text.strip():
        return response
    if generated.text == request.seeded:
        return response

    log.info(
        "replaced a seeded message with a generated one",
        extra={"kind": request.kind, "latency_ms": generated.latency_ms},
    )
    return _substitute(response, request, generated.text)


async def _generate(
    db: Session,
    journey: Journey,
    request: GenerationRequest,
    settings: Settings,
    on_block: object,
):
    """Dispatch to the right generator for this request kind."""
    if request.kind == "reexplain":
        return await reexplain(
            question_prompt=request.question_prompt,
            seeded=request.seeded,
            facts=request.facts,
            language=journey.language,  # type: ignore[arg-type]
            settings=settings,
            on_block=on_block,
        )

    if request.kind == "kfs_answer":
        return await answer_kfs_question(
            db,
            kfs_document_id=journey.kfs_document_id,
            question=request.customer_question,
            search_terms=request.search_terms,
            facts=request.facts,
            language=journey.language,  # type: ignore[arg-type]
            settings=settings,
            on_block=on_block,
        )

    log.warning("unknown generation kind", extra={"kind": request.kind})
    return None


def _substitute(response: TurnResponse, request: GenerationRequest, text: str) -> TurnResponse:
    """Swap the seeded text for the generated one, matching on content.

    Matched by text rather than by index, because the response's message list
    also contains the customer's own bubble and any earlier assistant lines -
    an index into `assistant_messages` is not an index into `messages`.
    """
    messages = list(response.messages)
    for index, message in enumerate(messages):
        if message.role == "assistant" and message.text == request.seeded:
            # The audio URL goes with the old text; `attach_audio` runs after
            # this and will synthesise or look up the new line.
            messages[index] = message.model_copy(update={"text": text, "audioUrl": None})
            break
    else:
        return response

    return response.model_copy(update={"messages": messages})
