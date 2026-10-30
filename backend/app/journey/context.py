"""The journey's working memory (`journeys.context`, build plan §9).

Everything the engine needs to decide the next step, and nothing else. It is a
Pydantic model rather than a loose dict so that a typo in one branch is a
validation error instead of a silently missing key three steps later, and so the
JSONB column has a documented shape.

**Nothing in here is trusted from a client.** Every field is written by the
engine from a validated action or from the database. A client can send an
`amount`; it cannot send `teachback_passed`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.journey.states import Lang


class PrefillData(BaseModel):
    """What the adapters returned, with the source each value came from."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    dob: str | None = None
    aadhaar_masked: str | None = None
    pan_masked: str | None = None
    ckyc_masked: str | None = None
    address: str | None = None
    shop_address: str | None = None
    mobile: str | None = None

    # Six-month average of AA credits, and the EMI the customer already pays.
    # The suitability decision is made from these two numbers.
    monthly_income: int | None = None
    existing_emi: int = 0

    # adapter name -> how long the mock took, for the dashboard's timeline.
    sources: dict[str, str] = Field(default_factory=dict)

    # True when the customer declined data sharing and typed it themselves, so
    # the receipt can say the income was self-declared rather than verified.
    self_declared: bool = False


class QuizProgress(BaseModel):
    """Teach-back state for one question."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    attempts: int = 0
    passed: bool = False
    first_attempt_correct: bool = False


class JourneyContext(BaseModel):
    """The whole of `journeys.context`."""

    model_config = ConfigDict(extra="forbid")

    # --- ASK_NEED ---
    amount: int | None = None
    purpose: str | None = None
    # How many times we have re-asked for the amount. Capped at one re-ask (§9):
    # after that the chips appear instead, because asking a third time in a
    # language the customer is struggling with is not going to help.
    amount_asks: int = 0

    # --- CONSENT_DATA ---
    consent_digilocker: bool = False
    consent_account_aggregator: bool = False
    consent_asked: bool = False

    # --- PREFILL / CONFIRM_DETAILS ---
    prefill: PrefillData = Field(default_factory=PrefillData)
    details_confirmed: bool = False

    # --- OFFERS ---
    offer_ids: list[str] = Field(default_factory=list)
    foir: float | None = None
    suitable: bool | None = None
    suitability_reasons: list[str] = Field(default_factory=list)

    # --- EXPLAIN_KFS ---
    # Which of explain_1..3 have been spoken. The customer can ask for a repeat
    # at any point, so this is a set of keys rather than a counter.
    explained: list[str] = Field(default_factory=list)

    # --- TEACHBACK ---
    quiz: list[QuizProgress] = Field(default_factory=list)
    quiz_index: int = 0
    teachback_passed: bool = False

    # --- TERMS_CONSENT ---
    terms_accepted: bool = False
    insurance_granted: bool = False
    terms_shown: list[str] = Field(default_factory=list)

    # --- OTP / RECEIPT ---
    otp_verified: bool = False
    receipt_no: str | None = None

    # --- cross-cutting ---
    # Consecutive turns we could not understand. Two in a row offers a human,
    # which is §13.7's escalation rule: repeated confusion is distress.
    confusion_streak: int = 0

    # Voice turns whose detected language differed from the journey's. Two in a
    # row prompts an offer to switch (§10.1).
    language_mismatch_streak: int = 0
    detected_language: Lang | None = None

    # Set when the journey was resumed from a rescue call, so the receipt can
    # record that the customer came back rather than finished in one sitting.
    resumed_from_rescue: bool = False

    turn_no: int = 0

    @classmethod
    def of(cls, stored: dict | None) -> JourneyContext:
        """Parse `journeys.context`, ignoring the `_meta` sibling.

        `_meta` holds render-only data - the prefill rows the card rebuilds
        from, the flag saying the client already chose a language - which no
        transition reads. It lives outside this model so that `extra="forbid"`
        keeps doing its job: a typo in a state field stays an error instead of
        being quietly absorbed.
        """
        data = dict(stored or {})
        data.pop("_meta", None)
        return cls.model_validate(data)

    def quiz_for(self, question_id: str) -> QuizProgress | None:
        return next((q for q in self.quiz if q.question_id == question_id), None)

    @property
    def quiz_passed_count(self) -> int:
        return sum(1 for q in self.quiz if q.passed)

    @property
    def consents_declined(self) -> bool:
        """True when the customer said no to everything we asked for.

        One grant is enough to continue: partial consent is a legitimate answer
        and must not be treated as a refusal (§9 CONSENT_DATA).
        """
        return (
            self.consent_asked
            and not self.consent_digilocker
            and not self.consent_account_aggregator
        )
