"""LLM understanding, as a **fallback** (build plan §10.3).

The rules in `journey/understand_rules.py` run first and handle the entire
golden path. This is for the long tail: a sentence phrased in a way the lexicon
does not cover, a question that is neither yes nor no, code-mixed speech with an
unusual word order.

The order matters. Rules-first means the demo's critical path has no model call
in it - it cannot be slowed by a cold start, broken by a quota, or made to say
something unexpected. The LLM only ever sees what the rules gave up on, and its
output is funnelled into the **same** `Understanding` shape, so the engine cannot
tell which path produced it and there is only one set of transitions to review.
"""

from __future__ import annotations

import logging

from app.ai.llm import (
    UNDERSTAND_SCHEMA,
    complete,
    facts_block,
    prompt,
    system_prompt,
    wrap_customer_text,
)
from app.ai.sarvam_client import SarvamError
from app.config import Settings
from app.journey.states import LANGUAGES, Lang
from app.journey.understand_rules import Intent, Understanding

log = logging.getLogger(__name__)


async def understand_with_llm(
    text: str,
    language: Lang,
    settings: Settings,
    *,
    step: str,
    offers: list[dict] | None = None,
    quiz_options: list[tuple[str, str]] | None = None,
) -> Understanding | None:
    """Classify an utterance the rules could not. None when unavailable.

    @param step          The current step, so the model knows what was asked.
    @param offers        `(offerId, lender)` context when offers are on screen.
    @param quiz_options  `(id, text)` pairs when a question is being asked.

    None rather than an exception: the caller already has a re-prompt path, and
    a failed classification must look the same as an unclassifiable one.
    """
    context = [f"The customer is at step {step}."]

    if offers:
        listed = ", ".join(
            f"{offer.get('offer_id', '?')} = {offer.get('lender', '?')}" for offer in offers
        )
        context.append(f"Offers on screen: {listed}.")

    if quiz_options:
        listed = "; ".join(f"{option_id}: {option_text}" for option_id, option_text in quiz_options)
        context.append(f"The question's options are: {listed}.")

    user = "\n\n".join([prompt("understand"), "\n".join(context), wrap_customer_text(text)])

    try:
        result = await complete(
            system=system_prompt(language),
            user=user,
            schema=UNDERSTAND_SCHEMA,
            schema_name="understanding",
            settings=settings,
        )
    except SarvamError as exc:
        log.info("llm understanding unavailable", extra={"kind": exc.kind})
        return None

    return _to_understanding(result.data, text)


def _to_understanding(data: dict, raw: str) -> Understanding | None:
    """Map the model's JSON onto the engine's own type.

    Anything unrecognised becomes None rather than `Intent.OTHER`, so the caller
    can tell "the model had no idea" from "the model was not asked".
    """
    raw_intent = data.get("intent")
    try:
        intent = Intent(raw_intent)
    except ValueError:
        log.info("llm returned an unknown intent", extra={"intent": str(raw_intent)})
        return None

    amount = data.get("amount")
    language = data.get("language")

    return Understanding(
        intent=intent,
        amount=int(amount) if isinstance(amount, (int, float)) else None,
        purpose=_as_text(data.get("purpose")),
        offer_hint=_as_text(data.get("offerId")),
        language=language if language in LANGUAGES else None,
        raw=raw,
        # The engine treats `confident=False` as "re-prompt", so a model reply
        # with no usable intent does not silently become a transition.
        confident=intent is not Intent.OTHER,
    )


def _as_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def quiz_option_from(data: dict) -> str | None:
    """The chosen option id, if the model identified one."""
    value = data.get("quizOptionId")
    return value if isinstance(value, str) and value.strip() else None


def is_distressed(data: dict) -> bool:
    """§13.7: distress escalates to a human."""
    return bool(data.get("distress"))


__all__ = ["facts_block", "is_distressed", "quiz_option_from", "understand_with_llm"]
