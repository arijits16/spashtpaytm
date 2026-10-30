"""Generating teach-back questions and explanation lines from a KFS (phase 11, item 3).

A newly ingested document needs the two pieces of writing a journey speaks: the
three explanation lines of EXPLAIN_KFS, and the three teach-back questions a
customer has to get right before consent unlocks. `sarvam-105b` writes them in
Marathi, Hindi and English with structured output.

**The model writes sentences; it never writes numbers.** Every figure is a
`{LATE_FEE}`-style placeholder that `journey/templates.py` fills from the
verified facts at render time - exactly as the seeded rows work. So the rule
"the AI never invents numbers" is enforced structurally here, not just checked
afterwards: there is no number in the generated text to be wrong.

It is checked afterwards anyway. Each line is rendered with the document's facts
and put through the Number Guard (§10.5), because a model asked for placeholders
will occasionally write "₹500" anyway, and the guard is what makes that a
rejected proposal instead of a sentence a customer hears. A rejected line falls
back to the seeded wording for the same fact, so a publish always yields a
complete, correct set.

Generation is **offline**: `live=False` selects `sarvam-105b` with reasoning on,
because an admin watching a spinner can afford the seconds a customer cannot.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import number_guard
from app.ai.llm import complete, facts_block, system_prompt
from app.ai.sarvam_client import SarvamError, demo_mode_active
from app.config import Settings
from app.db.models.catalog import TeachbackQuestion
from app.journey.states import LANGUAGES
from app.journey.templates import fill_question, render_with_facts

log = logging.getLogger(__name__)

# The three facts a customer must demonstrate they understood (§7.3). Kept
# identical to the seeded set so the dashboard's per-question pass-rate chart
# stays comparable across a KFS version change.
FACT_KEYS: tuple[str, ...] = ("late_fee", "total_repay", "insurance_optional")

SEEDED_QUESTION_IDS: dict[str, str] = {
    "late_fee": "q_late_fee",
    "total_repay": "q_total_repay",
    "insurance_optional": "q_insurance_optional",
}

EXPLANATION_KEYS: tuple[str, ...] = ("explain_1", "explain_2", "explain_3")

# The placeholders a generated line may use. Anything else is stripped by
# `fill_question`, which would leave a sentence with a hole in it - so the
# prompt lists these and the validation rejects a line that used another.
ALLOWED_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "PRINCIPAL",
        "EMI",
        "TENURE",
        "TOTAL_REPAY",
        "TOTAL_INTEREST",
        "TOTAL_COST",
        "PROCESSING_FEE",
        "GST",
        "NET_DISBURSED",
        "LATE_FEE",
        "INSURANCE_PREMIUM",
        "RATE_PA",
        "APR",
        "FORECLOSURE_PCT",
        "COOLING_OFF_DAYS",
        "LENDER",
    }
)

# Offline generation: a question in three languages with three options each is
# a lot of tokens, and the offline model reasons before it answers - a trivial
# reply measured 562 reasoning tokens - so the budget has to cover the thinking
# as well as the output. A truncated reply fails the schema and is discarded, so
# too small a budget looks exactly like a model that cannot follow instructions.
MAX_TOKENS = 3000

# Measured, not guessed. "Never write a number, write `{LATE_FEE}` instead" at
# temperature 0.2 with no penalty makes the model loop on the placeholder token
# - one run produced nine consecutive `{LATE_FEE}`s and then ran out of budget.
# A frequency penalty removes it completely, and a little more temperature keeps
# the Marathi and Hindi from reading like translated English.
GEN_TEMPERATURE = 0.4
FREQUENCY_PENALTY = 0.6
PRESENCE_PENALTY = 0.3

# No figure is mentioned more than twice in a two-sentence line. A line that
# repeats one is the degeneration above, caught even if the penalty does not
# prevent it.
MAX_PLACEHOLDER_REPEATS = 2

_LANG_FIELD = {"mr-IN": "mr", "hi-IN": "hi", "en-IN": "en"}

_PLACEHOLDER_RE = re.compile(r"\{([A-Z_]+)\}")

# Devanagari digits as well as Latin: the model writes "₹५००००" in Marathi.
_DIGITS_RE = re.compile(r"[0-9\u0966-\u096F]")


def _trilingual(description: str) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["mr", "hi", "en"],
        "description": description,
        "properties": {
            "mr": {"type": "string", "maxLength": 300},
            "hi": {"type": "string", "maxLength": 300},
            "en": {"type": "string", "maxLength": 300},
        },
    }


QUESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["prompt", "options", "reexplain", "rubric"],
    "properties": {
        "prompt": _trilingual("The question, one short sentence."),
        "options": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "correct", "text"],
                "properties": {
                    "id": {"type": "string", "enum": ["a", "b", "c"]},
                    "correct": {"type": "boolean"},
                    "text": _trilingual("The option, a short phrase."),
                },
            },
        },
        "reexplain": _trilingual("Two sentences explaining the fact more simply."),
        "rubric": {
            "type": "object",
            "additionalProperties": False,
            "required": ["mr", "hi", "en"],
            "properties": {
                "mr": {"type": "array", "maxItems": 8, "items": {"type": "string"}},
                "hi": {"type": "array", "maxItems": 8, "items": {"type": "string"}},
                "en": {"type": "array", "maxItems": 8, "items": {"type": "string"}},
            },
        },
    },
}

EXPLAIN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": list(EXPLANATION_KEYS),
    "properties": {key: _trilingual("Two short sentences.") for key in EXPLANATION_KEYS},
}


@dataclass(slots=True)
class Proposal:
    """What a publish proposes, before a human activates it.

    @param questions  Rows ready for `teachback_questions`, in `FACT_KEYS` order.
    @param explain    `{explain_1: {mr-IN, hi-IN, en-IN}, ...}`.
    @param engine     'sarvam-105b' or 'seeded' when the model was unavailable.
    @param blocked    Human-readable notes: which lines the guard rejected, and
                      which fell back to the seeded wording. Shown on the
                      dashboard, because "the AI wrote these" and "the AI wrote
                      these and two were rejected" are different claims.
    """

    questions: list[dict[str, Any]] = field(default_factory=list)
    explain: dict[str, dict[str, str]] = field(default_factory=dict)
    engine: str = "seeded"
    blocked: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "questions": self.questions,
            "explain": self.explain,
            "blocked": self.blocked,
        }


# --- validation --------------------------------------------------------------


def _placeholders(text: str) -> set[str]:
    return set(_PLACEHOLDER_RE.findall(text or ""))


def _has_digits(text: str) -> bool:
    """Any digit at all, Latin or Devanagari.

    The rule is absolute because a literal figure is wrong in two ways the
    Number Guard cannot see. One: the guard allows a number that matches a fact,
    so "Rs 50,000" passes when the principal is 50,000 - and is then quoted
    unchanged to a customer who asked for 75,000, because questions are rendered
    per journey from scaled facts. Two: a figure written into stored text
    survives a KFS revision that changes it. Placeholders have neither problem.
    """
    return bool(_DIGITS_RE.search(text or ""))


def _acceptable(text: str, facts: dict[str, Any]) -> bool:
    """Whether one generated string may be used.

    Two gates. An unknown placeholder would be stripped at render time and leave
    a sentence missing its figure, so it is rejected. And the *rendered* text
    goes through the Number Guard, which catches a literal number the model
    wrote instead of a placeholder.
    """
    if not text or not text.strip():
        return False

    if _has_digits(text):
        return False

    used = _placeholders(text)
    if not used <= ALLOWED_PLACEHOLDERS:
        return False

    if any(text.count("{" + name + "}") > MAX_PLACEHOLDER_REPEATS for name in used):
        return False

    rendered = fill_question({"en-IN": text}, "en-IN", facts)
    return number_guard.check(rendered, offers=[facts]).allowed


def _trilingual_ok(block: Any, facts: dict[str, Any]) -> dict[str, str] | None:
    """Validate one `{mr, hi, en}` block, returning it keyed by `Lang`."""
    if not isinstance(block, dict):
        return None

    out: dict[str, str] = {}
    placeholders: set[str] | None = None

    for language in LANGUAGES:
        text = block.get(_LANG_FIELD[language])
        if not isinstance(text, str) or not _acceptable(text, facts):
            return None

        # The three languages must quote the *same* figures. One run produced an
        # option reading "your monthly payment is {EMI}" in English and
        # "{PRINCIPAL}" in Marathi - two different claims presented as one
        # option, which is worse than no option at all in a product whose whole
        # premise is that the customer understood what they agreed to.
        used = _placeholders(text)
        if placeholders is None:
            placeholders = used
        elif used != placeholders:
            return None

        out[language] = text.strip()
    return out


# --- the seeded fallback -----------------------------------------------------


def seeded_question(db: Session, fact_key: str) -> TeachbackQuestion | None:
    """The seeded row for a fact, used when generation fails or is rejected."""
    return db.scalar(
        select(TeachbackQuestion).where(
            TeachbackQuestion.id == SEEDED_QUESTION_IDS.get(fact_key, "")
        )
    )


def _from_seeded(db: Session, fact_key: str, order: int) -> dict[str, Any] | None:
    row = seeded_question(db, fact_key)
    if row is None:
        return None
    return {
        "factKey": fact_key,
        "sortOrder": order,
        "prompt": dict(row.prompt),
        "options": [dict(option) for option in row.options],
        "reexplain": dict(row.reexplain),
        "rubric": dict(row.rubric),
        "origin": "seeded",
    }


def seeded_explanations(facts: dict[str, Any]) -> dict[str, dict[str, str]]:
    """The template explanation lines, already filled - the always-available set."""
    return {
        key: {language: render_with_facts(key, language, facts) for language in LANGUAGES}
        for key in EXPLANATION_KEYS
    }


# --- generation --------------------------------------------------------------


def _system(facts: dict[str, Any]) -> str:
    placeholders = ", ".join(sorted(f"{{{name}}}" for name in ALLOWED_PLACEHOLDERS))
    return system_prompt(
        "en-IN",
        extra=(
            "You are writing teach-back material for a Key Fact Statement that a "
            "compliance officer will review before any customer sees it.\n\n"
            "Rules you must follow exactly:\n"
            "1. NEVER write a number, amount, rate, percentage or date. Use a "
            f"placeholder instead. The only placeholders allowed are: {placeholders}.\n"
            "2. Write every field in all three languages: Marathi (mr), Hindi (hi) "
            "and Indian English (en). The Marathi and Hindi must be natural speech, "
            "not translated English word order.\n"
            "3. Exactly one option is correct. The two wrong options must be "
            "plausible misunderstandings, not jokes.\n"
            "4. Short sentences. This is read aloud to someone who may not read "
            "well, and spoken by a text-to-speech voice.\n"
            "5. The rubric is a list of keywords that would appear in a correct "
            "spoken answer in that language. No placeholders in the rubric.\n\n"
            f"{facts_block(facts)}\n"
            "The facts are given so you know what the document says. Do not repeat "
            "any of those numbers in your text; reference them with placeholders."
        ),
    )


_QUESTION_BRIEF: dict[str, str] = {
    "late_fee": (
        "Write a multiple-choice question asking what happens if an EMI is paid "
        "late. The correct option names the late fee per instalment and the drop "
        "in the CIBIL credit score. The other two are common wrong beliefs: that "
        "nothing happens, and that the loan is cancelled. Do not write a yes/no "
        "comprehension check - the three options must be three different outcomes."
    ),
    "total_repay": (
        "Write a multiple-choice question asking how much the customer will repay "
        "in total over the whole tenure. The correct option is the total "
        "repayable. The other two are the amount borrowed and one monthly "
        "instalment - the two figures people confuse it with. The three options "
        "must be three different amounts, not a yes/no check."
    ),
    "insurance_optional": (
        "Write a multiple-choice question asking whether the credit-life insurance "
        "is compulsory. The correct option says it is optional and the loan is "
        "sanctioned on identical terms without it. The other two are the common "
        "wrong beliefs: that it is compulsory, and that refusing it raises the "
        "interest rate. Three different answers, not a yes/no check."
    ),
}


async def _generate_question(
    fact_key: str,
    order: int,
    facts: dict[str, Any],
    settings: Settings,
    seeded_rubric: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """One question in three languages, or None if it cannot be trusted."""
    result = await complete(
        system=_system(facts),
        user=_QUESTION_BRIEF[fact_key],
        schema=QUESTION_SCHEMA,
        schema_name="teachback_question",
        settings=settings,
        live=False,
        max_tokens=MAX_TOKENS,
        temperature=GEN_TEMPERATURE,
        frequency_penalty=FREQUENCY_PENALTY,
        presence_penalty=PRESENCE_PENALTY,
    )

    data = result.data
    prompt = _trilingual_ok(data.get("prompt"), facts)
    reexplain = _trilingual_ok(data.get("reexplain"), facts)
    if prompt is None or reexplain is None:
        return None

    raw_options = data.get("options")
    if not isinstance(raw_options, list) or len(raw_options) != 3:
        return None

    options: list[dict[str, Any]] = []
    for entry in raw_options:
        if not isinstance(entry, dict):
            return None
        text = _trilingual_ok(entry.get("text"), facts)
        if text is None:
            return None
        options.append(
            {"id": str(entry.get("id")), "correct": bool(entry.get("correct")), "text": text}
        )

    # Exactly one correct answer. A set with none or two is not a question.
    if sum(1 for option in options if option["correct"]) != 1:
        return None

    rubric_raw = data.get("rubric") if isinstance(data.get("rubric"), dict) else {}
    rubric = {
        language: [
            term.strip()
            for term in (rubric_raw.get(_LANG_FIELD[language]) or [])
            if isinstance(term, str) and term.strip() and not _placeholders(term)
        ]
        for language in LANGUAGES
    }
    if any(not terms for terms in rubric.values()):
        # The rubric only grades *spoken* answers before the LLM is asked, and
        # the seeded keywords for this fact are still correct for a new
        # document. Falling back to them keeps a good question rather than
        # discarding it over its weakest field.
        if not seeded_rubric:
            return None
        rubric = {language: list(seeded_rubric.get(language) or []) for language in LANGUAGES}
        if any(not terms for terms in rubric.values()):
            return None

    return {
        "factKey": fact_key,
        "sortOrder": order,
        "prompt": prompt,
        "options": options,
        "reexplain": reexplain,
        "rubric": rubric,
        "origin": "generated",
    }


async def _generate_explanations(
    facts: dict[str, Any], settings: Settings
) -> dict[str, dict[str, str]] | None:
    result = await complete(
        system=_system(facts),
        user=(
            "Write the three lines that explain this loan to the customer out loud, "
            "in order. explain_1: what they are borrowing and what they will pay "
            "each month. explain_2: what it costs in total, including fees. "
            "explain_3: the one thing most likely to cost them money by surprise - "
            "the late fee and the foreclosure charge."
        ),
        schema=EXPLAIN_SCHEMA,
        schema_name="kfs_explanations",
        settings=settings,
        live=False,
        max_tokens=MAX_TOKENS,
        temperature=GEN_TEMPERATURE,
        frequency_penalty=FREQUENCY_PENALTY,
        presence_penalty=PRESENCE_PENALTY,
    )

    lines: dict[str, dict[str, str]] = {}
    for key in EXPLANATION_KEYS:
        block = _trilingual_ok(result.data.get(key), facts)
        if block is None:
            return None
        lines[key] = block
    return lines


async def propose(db: Session, facts: dict[str, Any], settings: Settings) -> Proposal:
    """Generate the publish proposal, falling back to seeded wording per item.

    Never raises. A publish must be possible with no network: the fallback is
    the seeded question bank and the seeded explanation templates, which is the
    same material the golden path already uses (§10.6).
    """
    proposal = Proposal(explain=seeded_explanations(facts))

    if demo_mode_active(settings):
        proposal.blocked.append("demo mode: the seeded questions and lines were used")
        proposal.questions = [
            row
            for index, key in enumerate(FACT_KEYS)
            if (row := _from_seeded(db, key, index + 1)) is not None
        ]
        return proposal

    tasks = [
        _generate_question(key, index + 1, facts, settings) for index, key in enumerate(FACT_KEYS)
    ]
    tasks.append(_generate_explanations(facts, settings))  # type: ignore[arg-type]

    outcomes = await asyncio.gather(*tasks, return_exceptions=True)
    *question_outcomes, explain_outcome = outcomes

    any_generated = False

    for index, (key, outcome) in enumerate(zip(FACT_KEYS, question_outcomes, strict=True)):
        if isinstance(outcome, SarvamError):
            proposal.blocked.append(f"{key}: generation failed ({outcome.kind}); seeded wording")
        elif isinstance(outcome, BaseException):
            log.exception("question generation raised", exc_info=outcome)
            proposal.blocked.append(f"{key}: generation raised; seeded wording")
        elif outcome is None:
            proposal.blocked.append(
                f"{key}: rejected by the number guard or the schema; seeded wording"
            )
        else:
            any_generated = True
            proposal.questions.append(outcome)
            continue

        fallback = _from_seeded(db, key, index + 1)
        if fallback is not None:
            proposal.questions.append(fallback)

    if isinstance(explain_outcome, dict):
        proposal.explain = explain_outcome
        any_generated = True
    else:
        if isinstance(explain_outcome, BaseException):
            proposal.blocked.append("explanation lines: generation failed; seeded lines")
        else:
            proposal.blocked.append("explanation lines: rejected; seeded lines")

    proposal.engine = settings.sarvam_llm_offline_model if any_generated else "seeded"
    proposal.questions.sort(key=lambda row: row["sortOrder"])
    return proposal
