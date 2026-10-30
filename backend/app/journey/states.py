"""The journey's steps and the 6-step progress bar (build plan §8.4, §9).

Two separate things live here and the distinction matters:

* **`Step`** is the engine's internal state - fourteen of them, including the
  ones a happy path never visits (`MANUAL_FORM`, `HUMAN_HANDOFF`).
* **The progress bar** is what the customer sees - six stages with Marathi,
  Hindi and English labels. Several steps map to one stage, because
  "Details" covering consent, prefill and confirmation is honest from the
  customer's point of view and a fourteen-segment bar is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

Lang = Literal["mr-IN", "hi-IN", "en-IN"]

# The product's amount bounds (§9 ASK_NEED). Mirrored as validation limits in
# `responses.py`; defined here because the engine and the amount card both need
# them and neither should import the request models for a constant.
AMOUNT_MIN_DEFAULT = 10_000
AMOUNT_MAX_DEFAULT = 200_000
LANGUAGES: tuple[Lang, ...] = ("mr-IN", "hi-IN", "en-IN")
DEFAULT_LANGUAGE: Lang = "mr-IN"


class Step(StrEnum):
    """Where a journey is. The string value is what crosses the wire."""

    INTRO = "INTRO"
    ASK_NEED = "ASK_NEED"
    CONSENT_DATA = "CONSENT_DATA"
    MANUAL_FORM = "MANUAL_FORM"
    PREFILL = "PREFILL"
    CONFIRM_DETAILS = "CONFIRM_DETAILS"
    OFFERS = "OFFERS"
    EXPLAIN_KFS = "EXPLAIN_KFS"
    TEACHBACK = "TEACHBACK"
    TERMS_CONSENT = "TERMS_CONSENT"
    OTP = "OTP"
    RECEIPT = "RECEIPT"
    DONE = "DONE"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"


class Status(StrEnum):
    """A journey's lifecycle. `abandoned` is set by the rescue scheduler, never
    by a client - a customer who closed the app has not decided anything."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    NEEDS_HUMAN = "needs_human"


# The six stages, in order, with the label in each language (§5.6).
PROGRESS_STAGES: tuple[tuple[str, dict[str, str]], ...] = (
    ("bolo", {"mr-IN": "बोलो", "hi-IN": "बोलो", "en-IN": "Speak"}),
    ("details", {"mr-IN": "माहिती", "hi-IN": "जानकारी", "en-IN": "Details"}),
    ("offers", {"mr-IN": "ऑफर", "hi-IN": "ऑफर", "en-IN": "Offers"}),
    ("samjho", {"mr-IN": "समजून घ्या", "hi-IN": "समझो", "en-IN": "Understand"}),
    ("check", {"mr-IN": "तपासणी", "hi-IN": "जाँच", "en-IN": "Check"}),
    ("done", {"mr-IN": "झालं", "hi-IN": "हो गया", "en-IN": "Done"}),
)

# Step -> (stage index, seconds of work still ahead). The ETA is a seeded
# estimate rather than a measurement: it only has to be honest about the shape
# of what is left, and a bar that jumps around because one customer was slow is
# worse than one that is approximately right.
_STEP_STAGE: dict[Step, tuple[int, int]] = {
    Step.INTRO: (0, 120),
    Step.ASK_NEED: (0, 110),
    Step.CONSENT_DATA: (1, 95),
    Step.MANUAL_FORM: (1, 110),
    Step.PREFILL: (1, 80),
    Step.CONFIRM_DETAILS: (1, 70),
    Step.OFFERS: (2, 55),
    Step.EXPLAIN_KFS: (3, 45),
    Step.TEACHBACK: (3, 35),
    Step.TERMS_CONSENT: (4, 20),
    Step.OTP: (4, 12),
    Step.RECEIPT: (5, 0),
    Step.DONE: (5, 0),
    # A handoff is not progress. It keeps the customer's place on the bar so
    # the screen does not imply they have lost the work they did.
    Step.HUMAN_HANDOFF: (4, 0),
}


@dataclass(frozen=True, slots=True)
class Progress:
    """The `progress` object of a `TurnResponse` (§8.4)."""

    index: int
    total: int
    label: str
    etaSeconds: int


def progress_for(step: Step, language: str) -> Progress:
    """The progress bar for a step, labelled in the journey's language."""
    index, eta = _STEP_STAGE[step]
    _, labels = PROGRESS_STAGES[index]
    return Progress(
        index=index,
        total=len(PROGRESS_STAGES),
        label=labels.get(language, labels["en-IN"]),
        etaSeconds=eta,
    )


# Steps from which a stalled journey is worth a rescue call (§9, phase 10).
# Earlier than PREFILL there is nothing to resume to, and past OTP the customer
# has either finished or is being called by a human anyway.
RESCUABLE_STEPS: frozenset[Step] = frozenset(
    {Step.PREFILL, Step.OFFERS, Step.TEACHBACK, Step.CONFIRM_DETAILS, Step.EXPLAIN_KFS}
)

# Steps where the journey is over, one way or another.
TERMINAL_STEPS: frozenset[Step] = frozenset({Step.DONE, Step.HUMAN_HANDOFF})
