"""Re-explaining, and answering questions from the KFS (plan §10.3, §10.5).

Both functions generate prose, so both pass through the Number Guard before
returning. The guard's fallback is always the seeded text, which means a blocked
generation costs the customer fluency and never costs them accuracy.

`answer_kfs_question` is the one place the model is allowed to answer a question
rather than rephrase an answer, and it is tightly bounded: full-text search over
`kfs_clauses` supplies the clauses, the prompt forbids going beyond them, and no
match at all produces an offer of a human expert rather than a guess.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.llm import (
    TEXT_SCHEMA,
    complete,
    facts_block,
    prompt,
    system_prompt,
    wrap_customer_text,
)
from app.ai.number_guard import GuardVerdict, guard
from app.ai.sarvam_client import SarvamError
from app.config import Settings
from app.db.models.catalog import KfsClause
from app.journey.states import Lang
from app.journey.templates import render

log = logging.getLogger(__name__)

# How many clauses to put in front of the model. Three is enough for any
# question this product fields, and a bigger window just invites it to answer
# from a clause the customer did not ask about.
MAX_CLAUSES = 3


@dataclass(frozen=True, slots=True)
class Generated:
    """Generated text, with what the guard made of it."""

    text: str
    guarded: bool
    verdict: GuardVerdict | None
    latency_ms: int

    @property
    def used_fallback(self) -> bool:
        return self.guarded


async def reexplain(
    *,
    question_prompt: str,
    seeded: str,
    facts: dict,
    language: Lang,
    settings: Settings,
    previous_attempt: str | None = None,
    on_block: object = None,
) -> Generated:
    """Explain a point again, more simply.

    @param seeded  The seeded re-explanation. Used verbatim if the model is
                   unavailable or its text is blocked, so this function always
                   returns something a customer can be shown.
    """
    instructions = [
        prompt("reexplain").replace("{LANGUAGE}", language),
        f"The point to explain: {question_prompt}",
        facts_block(facts),
    ]
    if previous_attempt:
        instructions.append(
            f"You already said this, and it did not work, so do not repeat it:\n{previous_attempt}"
        )

    try:
        result = await complete(
            system=system_prompt(language),
            user="\n\n".join(instructions),
            schema=TEXT_SCHEMA,
            schema_name="reexplanation",
            settings=settings,
        )
    except SarvamError as exc:
        log.info("llm reexplanation unavailable", extra={"kind": exc.kind})
        return Generated(text=seeded, guarded=False, verdict=None, latency_ms=0)

    candidate = str(result.data.get("text") or "").strip()
    if not candidate:
        return Generated(text=seeded, guarded=False, verdict=None, latency_ms=result.latency_ms)

    text, verdict = guard(candidate, seeded, offers=[facts], on_block=on_block)
    return Generated(
        text=text,
        guarded=not verdict.allowed,
        verdict=verdict,
        latency_ms=result.latency_ms,
    )


# Words that match every clause and so rank nothing. Postgres' own English
# stop-word list does not include these, because in general prose they are
# meaningful - here they are not.
_NOISE_WORDS = frozenset({"loan", "my", "i", "the", "a", "will", "what", "how", "is", "it"})


def _or_query(text: str) -> str:
    """Build an OR tsquery from a person's question.

    **OR, not AND.** `websearch_to_tsquery` and `plainto_tsquery` both AND the
    terms, which is right for a search box and wrong here: "what happens if I
    close the loan early" would require every one of those words to appear in a
    single clause, and no clause contains "happens". The customer is asking one
    question in their own words, so any strong term matching is a hit and
    `ts_rank` decides which clause answers it best.
    """
    words = [word for word in re.findall(r"[A-Za-z]{3,}", text.lower()) if word not in _NOISE_WORDS]
    # Deduplicated, order preserved, so a repeated word does not skew the rank.
    unique = list(dict.fromkeys(words))
    return " | ".join(unique)


def search_clauses(
    db: Session, kfs_document_id, query: str, limit: int = MAX_CLAUSES
) -> list[KfsClause]:
    """Full-text search this loan's KFS clauses (§10.3).

    Scoped to **this** document: answering from another lender's terms would be
    confidently wrong in the most damaging possible way.
    """
    if not kfs_document_id or not query.strip():
        return []

    expression = _or_query(query)
    if not expression:
        return []

    # `to_tsquery` because the expression is ours, built from extracted words -
    # the customer's punctuation never reaches it.
    tsquery = func.to_tsquery("english", expression)
    return list(
        db.scalars(
            select(KfsClause)
            .where(KfsClause.kfs_document_id == kfs_document_id)
            .where(KfsClause.tsv.op("@@")(tsquery))
            .order_by(func.ts_rank(KfsClause.tsv, tsquery).desc())
            .limit(limit)
        ).all()
    )


async def answer_kfs_question(
    db: Session,
    *,
    kfs_document_id,
    question: str,
    search_terms: str,
    facts: dict,
    language: Lang,
    settings: Settings,
    on_block: object = None,
) -> Generated | None:
    """Answer a question about the terms, from the clauses only.

    @param search_terms  English keywords for the full-text search. The
                         customer asks in Marathi and the clauses are in
                         English, so the caller maps the question to terms
                         (`understand_rules` does this from its lexicon) rather
                         than translating the whole question first.

    Returns None when no clause matches, which the caller turns into an offer of
    a human expert (§10.3). That is the honest answer: the document does not say,
    so we do not either.
    """
    clauses = search_clauses(db, kfs_document_id, search_terms or question)
    if not clauses:
        log.info("no KFS clause matched the question")
        return None

    rendered = "\n\n".join(
        f"[{clause.clause_key}] {clause.title}\n{clause.text_en}" for clause in clauses
    )

    user = "\n\n".join(
        [
            prompt("kfs_answer").replace("{LANGUAGE}", language),
            f"<clauses>\n{rendered}\n</clauses>",
            facts_block(facts),
            wrap_customer_text(question),
        ]
    )

    try:
        result = await complete(
            system=system_prompt(language),
            user=user,
            schema=TEXT_SCHEMA,
            schema_name="kfs_answer",
            settings=settings,
        )
    except SarvamError as exc:
        log.info("llm kfs answer unavailable", extra={"kind": exc.kind})
        return None

    candidate = str(result.data.get("text") or "").strip()
    if not candidate:
        return None

    # The fallback here is the didnt_catch line rather than an explanation: if
    # the guard rejected the answer, we do not have a correct one to substitute.
    fallback = render("didnt_catch", language)
    text, verdict = guard(candidate, fallback, offers=[facts], on_block=on_block)

    return Generated(
        text=text,
        guarded=not verdict.allowed,
        verdict=verdict,
        latency_ms=result.latency_ms,
    )
