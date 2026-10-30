"""Teach-back: three questions, up to three attempts each (build plan §9, §7.3).

This is the part that makes the product more than a nicer loan form. A customer
cannot agree to the terms until they have demonstrated they understand them, and
the attempt record becomes evidence on the receipt.

Design decisions worth stating:

* **Three attempts, not unlimited.** One answer plus two re-explanations. After
  that, a customer who still has it wrong is not helped by a fourth phrasing -
  they are handed to a human, and consent stays locked.
* **First-attempt correctness is recorded separately.** Passing on the third try
  is a pass, but a question that 40% of customers get wrong first time is a
  badly-worded KFS, and the dashboard charts exactly that (§12).
* **Keyword grading before any model.** A spoken answer is graded against the
  seeded rubric first. The LLM (phase 8) only sees what the rubric could not
  decide, so the golden path never depends on a model call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.catalog import TeachbackQuestion
from app.journey.states import Lang
from app.journey.templates import fill_question
from app.journey.understand_rules import normalise

# §9: 1 answer + 2 re-explanations.
MAX_ATTEMPTS = 3

# How many questions a journey asks. The bank holds a spare (§7.3).
QUESTIONS_PER_JOURNEY = 3


@dataclass(frozen=True, slots=True)
class RenderedOption:
    id: str
    text: str
    correct: bool


@dataclass(frozen=True, slots=True)
class RenderedQuestion:
    """One question with every `{PLACEHOLDER}` already filled from the offer.

    `correct_option_id` stays server-side: the card sent to the client carries
    only ids and texts, so the answer is never in the payload.
    """

    id: str
    index: int
    total: int
    prompt: str
    options: tuple[RenderedOption, ...]
    reexplain: str
    rubric: tuple[str, ...]
    fact_key: str

    @property
    def correct_option_id(self) -> str:
        return next(option.id for option in self.options if option.correct)


def active_questions(db: Session) -> list[TeachbackQuestion]:
    """The questions a journey asks, in order."""
    return list(
        db.scalars(
            select(TeachbackQuestion)
            .where(TeachbackQuestion.active.is_(True))
            .order_by(TeachbackQuestion.sort_order)
            .limit(QUESTIONS_PER_JOURNEY)
        ).all()
    )


def render(
    question: TeachbackQuestion,
    language: Lang,
    facts: dict[str, Any],
    index: int,
    total: int,
) -> RenderedQuestion:
    """Fill one question's text from the selected offer's facts."""
    options = tuple(
        RenderedOption(
            id=str(option["id"]),
            text=fill_question(option["text"], language, facts),
            correct=bool(option.get("correct", False)),
        )
        for option in question.options
    )

    rubric_terms = tuple(
        fill_question({language: term}, language, facts)
        for term in (question.rubric or {}).get(language, [])
    )

    return RenderedQuestion(
        id=question.id,
        index=index,
        total=total,
        prompt=fill_question(question.prompt, language, facts),
        options=options,
        reexplain=fill_question(question.reexplain, language, facts),
        rubric=rubric_terms,
        fact_key=question.kfs_fact_key,
    )


@dataclass(frozen=True, slots=True)
class Grade:
    """The verdict on one answer.

    `confidence` is 1.0 for a tapped option - there is nothing to interpret -
    and lower for a spoken one. Below 0.6 the engine asks the customer to tap
    instead of guessing on their behalf (§10.3).
    """

    correct: bool
    grader: str
    confidence: float
    matched: tuple[str, ...] = ()


# A tapped option is unambiguous.
TAP_CONFIDENCE = 1.0

# §10.3: below this the engine asks for a tap rather than deciding.
MIN_CONFIDENCE = 0.6


def grade_option(question: RenderedQuestion, option_id: str) -> Grade:
    """Grade a tapped option."""
    return Grade(
        correct=option_id == question.correct_option_id,
        grader="rule",
        confidence=TAP_CONFIDENCE,
    )


def grade_free_text(question: RenderedQuestion, answer: str) -> Grade:
    """Grade a spoken or typed answer against the seeded rubric.

    Two of the rubric's keywords must appear for a pass. One is too weak -
    "CIBIL" alone could come from "will this affect my CIBIL score?", which is a
    question, not an understanding - and requiring all of them would fail a
    customer who explained it correctly in their own words.

    `confidence` reflects how much of the rubric matched, so a one-keyword
    answer comes back as *uncertain* rather than as a fail: the engine then asks
    for a tap instead of telling someone they are wrong when they may not be.
    """
    if not question.rubric:
        return Grade(correct=False, grader="rule", confidence=0.0)

    normalised = normalise(answer)
    matched = tuple(term for term in question.rubric if term and normalise(term) in normalised)

    # Also accept the correct option read aloud, which is what a customer who
    # can see the card actually does.
    correct_text = next(o.text for o in question.options if o.correct)
    if correct_text and normalise(correct_text) in normalised:
        return Grade(correct=True, grader="rule", confidence=1.0, matched=matched)

    hits = len(matched)
    if hits >= 2:
        return Grade(
            correct=True,
            grader="rule",
            confidence=min(1.0, 0.6 + 0.2 * hits),
            matched=matched,
        )
    if hits == 1:
        # Uncertain, not wrong.
        return Grade(correct=False, grader="rule", confidence=0.4, matched=matched)
    return Grade(correct=False, grader="rule", confidence=0.2)


def kfs_lines(facts: dict[str, Any], language: Lang) -> list[dict[str, Any]]:
    """ "Your loan in 5 lines" (§5.6 KFS card).

    Five lines, three of them flagged red. The red ones are the charges a
    customer finds out about afterwards if nobody tells them now - the late fee,
    the foreclosure charge, and the fee deducted before the money arrives. The
    flag is what the app renders in red, so what gets emphasised is decided here
    and not by a designer in the client.
    """
    from app.journey.templates import format_rupees

    red_flag_fee = facts.get("processing_fee", 0) > 0

    texts: dict[str, dict[Lang, str]] = {
        "emi": {
            "mr-IN": f"दर महिन्याला ₹{format_rupees(facts['emi'])}, {facts['tenure_months']} महिने.",
            "hi-IN": f"हर महीने ₹{format_rupees(facts['emi'])}, {facts['tenure_months']} महीने।",
            "en-IN": f"₹{format_rupees(facts['emi'])} a month for {facts['tenure_months']} months.",
        },
        "total_repay": {
            "mr-IN": f"एकूण परतफेड ₹{format_rupees(facts['total_repay'])} (व्याज ₹{format_rupees(facts['total_interest'])}).",
            "hi-IN": f"कुल चुकाना ₹{format_rupees(facts['total_repay'])} (ब्याज ₹{format_rupees(facts['total_interest'])})।",
            "en-IN": f"You repay ₹{format_rupees(facts['total_repay'])} in all (₹{format_rupees(facts['total_interest'])} interest).",
        },
        "processing_fee": {
            "mr-IN": f"शुल्क ₹{format_rupees(facts['processing_fee'])} + GST ₹{format_rupees(facts['gst'])} आधीच कापलं जाईल; हातात ₹{format_rupees(facts['net_disbursed'])} मिळतील.",
            "hi-IN": f"फीस ₹{format_rupees(facts['processing_fee'])} + GST ₹{format_rupees(facts['gst'])} पहले ही कटेगी; हाथ में ₹{format_rupees(facts['net_disbursed'])} आएँगे।",
            "en-IN": f"A ₹{format_rupees(facts['processing_fee'])} fee + ₹{format_rupees(facts['gst'])} GST is deducted first, so you receive ₹{format_rupees(facts['net_disbursed'])}.",
        },
        "late_fee": {
            "mr-IN": f"EMI उशिरा भरला तर ₹{format_rupees(facts['late_fee'])} दंड आणि CIBIL स्कोर कमी होऊ शकतो.",
            "hi-IN": f"EMI देर से भरी तो ₹{format_rupees(facts['late_fee'])} लेट फीस और CIBIL स्कोर गिर सकता है।",
            "en-IN": f"A late EMI costs ₹{format_rupees(facts['late_fee'])} and can lower your CIBIL score.",
        },
        "foreclosure_pct": {
            "mr-IN": f"मुदतीआधी बंद केलं तर बाकी रकमेवर {facts['foreclosure_pct']:g}% शुल्क.",
            "hi-IN": f"समय से पहले बंद किया तो बाकी रकम पर {facts['foreclosure_pct']:g}% चार्ज।",
            "en-IN": f"Closing early costs {facts['foreclosure_pct']:g}% of the balance.",
        },
        "insurance_optional": {
            "mr-IN": f"विमा ऐच्छिक आहे (₹{format_rupees(facts['insurance_premium'])}). नाही म्हणता येतं.",
            "hi-IN": f"बीमा वैकल्पिक है (₹{format_rupees(facts['insurance_premium'])})। मना कर सकते हैं।",
            "en-IN": f"Insurance is optional (₹{format_rupees(facts['insurance_premium'])}). You can say no.",
        },
    }

    # The fee line only earns a place when there is a fee; without one it would
    # be noise, and the fifth slot is better spent on the cooling-off right.
    keys = ["emi", "total_repay"]
    if red_flag_fee:
        keys.append("processing_fee")
    keys += ["late_fee", "foreclosure_pct", "insurance_optional"]

    red_flags = {"processing_fee", "late_fee", "foreclosure_pct"}

    return [
        {
            "key": key,
            "text": texts[key].get(language, texts[key]["en-IN"]),
            "redFlag": key in red_flags,
        }
        for key in keys
    ]
