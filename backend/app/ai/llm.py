"""The brain: Sarvam-105B with structured output (build plan §10.3, §13.7).

The model's job is narrow by design. It **understands** and it **phrases**. It
does not decide anything: no transition, no consent, no offer choice, no pass or
fail. Those are `journey/engine.py`, which is deterministic Python a regulator
could read (§9).

Three controls make that narrowness real rather than aspirational:

1. **Structured output.** Every call declares a JSON schema and a reply that
   does not match it is discarded. A model that returns prose where an enum was
   expected gets no say in what happens next.
2. **The Number Guard** (§10.5) runs on all generated prose, so an invented
   figure cannot reach a customer even if everything else here fails.
3. **Customer text is wrapped in `<customer_said>` tags** and the system prompt
   names it as data. Prompt injection is treated as the *normal* case, not an
   attack to be detected: speech is untrusted input, and the controls that matter
   are the two above, which hold regardless of what the model was told.

**Minimal context** (§13.7): the model sees this journey's facts, the customer's
first name, and the language. No other users' data, no secrets, no masked
identifiers, no transcript history beyond the current turn.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.ai.sarvam_client import SarvamError, client_for
from app.config import Settings
from app.journey.states import Lang

log = logging.getLogger(__name__)

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

# §10: temperature 0.2, reasoning off for live turns, 300 max tokens.
TEMPERATURE = 0.2
MAX_TOKENS = 300

LANGUAGE_NAMES: dict[Lang, str] = {
    "mr-IN": "Marathi (मराठी)",
    "hi-IN": "Hindi (हिंदी)",
    "en-IN": "Indian English",
}


@lru_cache(maxsize=8)
def prompt(name: str) -> str:
    """Load a prompt file, cached."""
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


def system_prompt(language: Lang, *, extra: str = "") -> str:
    """The system prompt, with the language filled in."""
    base = prompt("system").replace("{LANGUAGE}", LANGUAGE_NAMES[language])
    return f"{base}\n\n{extra}".strip() if extra else base


def wrap_customer_text(text: str) -> str:
    """Wrap untrusted speech so the prompt can name it as data (§13.7).

    The closing tag is neutralised in the text itself, so a customer cannot
    close the tag early and have the rest of their utterance read as prompt.
    That is the one piece of actual escaping here; the real defences are the
    schema and the guard.
    """
    sanitised = text.replace("</customer_said>", "[/]").replace("<customer_said>", "[]")
    return f"<customer_said>\n{sanitised}\n</customer_said>"


def facts_block(facts: dict[str, Any]) -> str:
    """The `<facts>` block: the only numbers the model may use."""
    numeric = {
        key: value
        for key, value in facts.items()
        if isinstance(value, (int, float, str)) and not isinstance(value, bool)
    }
    return "<facts>\n" + json.dumps(numeric, ensure_ascii=False, indent=2) + "\n</facts>"


# --- schemas ----------------------------------------------------------------
#
# Declared to the API as `response_format: json_schema`, so a non-conforming
# reply is the provider's problem rather than ours to parse defensively.

UNDERSTAND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent"],
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "provide_need",
                "yes",
                "no",
                "choose_offer",
                "answer_quiz",
                "didnt_understand",
                "want_human",
                "switch_language",
                "question_about_terms",
                "other",
            ],
        },
        "amount": {"type": ["integer", "null"]},
        "purpose": {"type": ["string", "null"]},
        "offerId": {"type": ["string", "null"]},
        "quizOptionId": {"type": ["string", "null"]},
        "freeAnswer": {"type": ["string", "null"]},
        "language": {"type": ["string", "null"], "enum": ["mr-IN", "hi-IN", "en-IN", None]},
        "distress": {"type": ["boolean", "null"]},
    },
}

GRADE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["correct", "confidence"],
    "properties": {
        "correct": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "missingConcept": {"type": ["string", "null"]},
    },
}

TEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {
        "text": {"type": "string", "maxLength": 400},
        "answered": {"type": ["boolean", "null"]},
    },
}


@dataclass(frozen=True, slots=True)
class LlmResult:
    """A structured reply, with its latency."""

    data: dict[str, Any]
    latency_ms: int


async def complete(
    *,
    system: str,
    user: str,
    schema: dict[str, Any],
    schema_name: str,
    settings: Settings,
    live: bool = True,
    max_tokens: int = MAX_TOKENS,
    reasoning: bool = False,
    temperature: float = TEMPERATURE,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
) -> LlmResult:
    """One structured LLM call.

    @param live  True during a customer turn, which selects the conversations
                 model and switches reasoning **off**: a reasoning pass costs
                 seconds the 4-second voice budget does not have (§10.4).
                 Offline work (phase 11 ingestion) passes False.
    @param reasoning  Off by default, for both live and offline work. Measured:
                 asked for one teach-back question with reasoning on, the
                 offline model spent 3,999 reasoning tokens and returned no
                 content at all - a truncated reply the schema then discarded.
                 Three short sentences in three languages need no chain of
                 thought, and §10 requires reasoning off on the live path.
    @param frequency_penalty  Zero on the live path. Phase 11 generation sets it,
                 because asking the model to write `{LATE_FEE}` instead of a
                 number makes it loop on that token: measured, a prompt with no
                 penalty produced "{LATE_FEE} {LATE_FEE} {LATE_FEE} ..." until
                 the budget ran out. 0.6 removes it entirely.
    @param max_tokens  300 for a live turn (§10). Phase 11 generates a whole
                 teach-back question in three languages in one call and needs
                 more room; a truncated reply fails the schema and is discarded,
                 so too small a budget looks like a model that cannot comply.

    Raises `SarvamError` on a failure or a malformed reply. Callers always have
    a seeded fallback, so an exception here is a degradation, not an outage.
    """
    client = client_for(settings)
    model = settings.sarvam_llm_live_model if live else settings.sarvam_llm_offline_model

    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "frequency_penalty": frequency_penalty,
        "presence_penalty": presence_penalty,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        },
    }
    if not reasoning:
        # §10: reasoning off for live turns - and off for offline generation
        # too, where it consumed the whole token budget before writing anything.
        body["reasoning_effort"] = None

    # Offline work gets the generous timeout class: it reasons before it
    # answers, and nobody is waiting on a four-second budget (§10.4).
    result = await client.post_json("/v1/chat/completions", body, kind="llm" if live else "offline")

    choices = result.payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise SarvamError("malformed", "chat completion had no choices")

    content = (choices[0].get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise SarvamError("malformed", "chat completion had no content")

    try:
        data = json.loads(content)
    except ValueError as exc:
        # The schema was declared, so this is the provider not honouring it.
        # Discarded rather than salvaged: a half-parsed intent is worse than
        # falling back to the rules.
        raise SarvamError("malformed", "chat completion was not valid JSON") from exc

    if not isinstance(data, dict):
        raise SarvamError("malformed", "chat completion was not a JSON object")

    return LlmResult(data=data, latency_ms=result.latency_ms)
