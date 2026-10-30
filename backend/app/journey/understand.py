"""Resolving what the customer meant (build plan §9, §10.3).

The engine is deterministic and synchronous on purpose, and the LLM is async and
fallible. This module is the seam between them: it produces an `Understanding`
**before** the engine runs, so the engine's transitions never await anything and
stay a pure function of (state, understood input).

Rules first, always. The LLM is asked only when the rules return
`confident=False`, which on the golden path is never - so the demo's critical
path has no model call in it and cannot be slowed, throttled or surprised by one.
"""

from __future__ import annotations

import logging

from app.ai.sarvam_client import demo_mode_active
from app.ai.understand_llm import understand_with_llm
from app.config import Settings
from app.journey.states import Lang
from app.journey.understand_rules import Understanding, understand

log = logging.getLogger(__name__)


async def resolve(
    text: str,
    *,
    language: Lang,
    step: str,
    settings: Settings,
    step_expects_amount: bool = False,
    lender_names: tuple[str, ...] = (),
    offers: list[dict] | None = None,
    quiz_options: list[tuple[str, str]] | None = None,
) -> Understanding:
    """Classify an utterance: rules, then the LLM if they were unsure.

    Returns the rules' own verdict when the LLM is unavailable or adds nothing,
    so the caller always gets an `Understanding` and the engine always has
    something to transition on.
    """
    rule_based = understand(
        text, step_expects_amount=step_expects_amount, lender_names=lender_names
    )

    if rule_based.confident:
        return rule_based

    if demo_mode_active(settings):
        # §10.6: no model calls in demo mode. The engine re-prompts, which is
        # the same behaviour the rules alone would produce.
        return rule_based

    enriched = await understand_with_llm(
        text,
        language,
        settings,
        step=step,
        offers=offers,
        quiz_options=quiz_options,
    )

    if enriched is None or not enriched.confident:
        return rule_based

    log.info(
        "llm understood an utterance the rules could not",
        extra={"intent": enriched.intent.value, "step": step},
    )
    return enriched
