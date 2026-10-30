"""Grading a free-form teach-back answer (build plan §10.3).

Two stages, rules first:

1. `journey/teachback.grade_free_text` matches the seeded rubric keywords. Fast,
   free, reviewable by a native speaker, and sufficient for an answer that uses
   the expected words.
2. This module, for an answer that is right but phrased differently. "If I'm
   late they'll fine me and the bank will know" contains none of the rubric's
   keywords and is a correct answer.

**Below 0.6 confidence the customer is asked to tap an option instead** (§10.3).
That is the important rule: telling someone they misunderstood a loan when they
did not is a worse failure than one extra tap, and this is the step that decides
whether they may agree at all.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ai.llm import GRADE_SCHEMA, complete, prompt, system_prompt, wrap_customer_text
from app.ai.sarvam_client import SarvamError
from app.config import Settings
from app.journey.states import Lang
from app.journey.teachback import MIN_CONFIDENCE, Grade, RenderedQuestion

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LlmGrade:
    grade: Grade
    missing_concept: str | None
    latency_ms: int


async def grade_with_llm(
    question: RenderedQuestion,
    answer: str,
    language: Lang,
    settings: Settings,
) -> LlmGrade | None:
    """Grade a free-form answer. None when the LLM is unavailable.

    The model is told the question and the correct answer, and asked only
    whether the customer's words carry the same meaning. It is not asked to
    decide anything else about the journey.
    """
    correct_option = next((o.text for o in question.options if o.correct), "")

    user = "\n\n".join(
        [
            prompt("grade"),
            f"Question: {question.prompt}",
            f"The correct answer is: {correct_option}",
            f"The concept being tested is: {question.fact_key}",
            wrap_customer_text(answer),
        ]
    )

    try:
        result = await complete(
            system=system_prompt(language),
            user=user,
            schema=GRADE_SCHEMA,
            schema_name="grade",
            settings=settings,
        )
    except SarvamError as exc:
        log.info("llm grading unavailable", extra={"kind": exc.kind})
        return None

    data = result.data
    correct = bool(data.get("correct"))
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))

    # An uncertain "correct" is not a pass. The engine reads `correct=False`
    # with a low confidence as "ask them to tap", which is the §10.3 rule.
    if correct and confidence < MIN_CONFIDENCE:
        log.info("llm grade too uncertain to pass", extra={"confidence": confidence})
        correct = False

    missing = data.get("missingConcept")

    return LlmGrade(
        grade=Grade(
            correct=correct,
            grader="llm",
            confidence=confidence,
        ),
        missing_concept=missing if isinstance(missing, str) and missing.strip() else None,
        latency_ms=result.latency_ms,
    )
