"""Card schemas - the server-driven UI contract (build plan §8.4).

The app and the website hold **no business logic** (plan rule 10). They render
whatever card the backend sends, which is why adding a step is a backend change
and why the same journey works identically on iOS and in a browser.

Every card is a discriminated union member keyed on `type`. Clients switch on
that string; an unknown value decodes to `.unsupported` on iOS and shows
"Please update the app" rather than crashing.

Money is whole rupees as integers and rates are two-decimal numbers (§8.1), so
no client ever has to decide how to round a figure the customer will be held to.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.journey.states import Lang


class CardModel(BaseModel):
    """Base for every card. `extra="forbid"` catches a field we meant to rename."""

    model_config = ConfigDict(extra="forbid")


# --- language ----------------------------------------------------------------


class LanguageOption(CardModel):
    language: Lang
    label: str


class LanguageCardData(CardModel):
    options: list[LanguageOption]


class LanguageCard(CardModel):
    type: Literal["language"] = "language"
    data: LanguageCardData


# --- amount ------------------------------------------------------------------


class AmountCardData(CardModel):
    """Suggested amounts plus the hard bounds the engine enforces anyway."""

    chips: list[int]
    min: int
    max: int


class AmountCard(CardModel):
    type: Literal["amount"] = "amount"
    data: AmountCardData


# --- consent -----------------------------------------------------------------


class ConsentPurpose(CardModel):
    """One data-sharing purpose.

    `granted` is typed `Literal[False]`: the card is the *offer* of consent and
    a pre-ticked consent box is not consent. The customer's answer travels back
    in the action, never as a default the server suggested.
    """

    id: Literal["fetch_digilocker", "fetch_account_aggregator"]
    title: str
    detail: str
    granted: Literal[False] = False


class ConsentCardData(CardModel):
    purposes: list[ConsentPurpose]
    why: str


class ConsentCard(CardModel):
    type: Literal["consent"] = "consent"
    data: ConsentCardData


# --- manual form -------------------------------------------------------------


class ManualFormField(CardModel):
    id: Literal["fullName", "dob", "monthlyIncome", "shopAddress", "mobile"]
    label: str
    kind: Literal["text", "date", "number", "phone"]
    required: bool


class ManualFormCardData(CardModel):
    fields: list[ManualFormField]


class ManualFormCard(CardModel):
    type: Literal["manual_form"] = "manual_form"
    data: ManualFormCardData


# --- prefill -----------------------------------------------------------------


class PrefillRow(CardModel):
    """One prefilled value and where it came from.

    The source is shown to the customer on purpose: "we filled this from
    DigiLocker" is the difference between a form that feels helpful and one that
    feels like surveillance.
    """

    label: str
    value: str
    source: Literal["DigiLocker", "CKYC", "Account Aggregator", "UPI AutoPay"]


class PrefillCardData(CardModel):
    rows: list[PrefillRow]


class PrefillCard(CardModel):
    type: Literal["prefill"] = "prefill"
    data: PrefillCardData


# --- confirm -----------------------------------------------------------------


class ConfirmField(CardModel):
    id: Literal["shopAddress", "mobile"]
    label: str
    value: str


class ConfirmCardData(CardModel):
    fields: list[ConfirmField]


class ConfirmCard(CardModel):
    type: Literal["confirm"] = "confirm"
    data: ConfirmCardData


# --- offers ------------------------------------------------------------------


class Suitability(CardModel):
    """Why this customer may or may not borrow this amount.

    `foirPct` is a percentage (16.2), not a fraction, because it is shown on
    screen. `reasons` are written for the customer, not for an underwriter.
    """

    foirPct: float
    decision: Literal["suitable", "not_suitable"]
    reasons: list[str]


class OfferSummary(CardModel):
    """One priced offer, with every number the comparison needs.

    `apr` is the figure the card renders in bold and the list is sorted by it.
    `totalCost` is what the customer loses - interest plus fee plus GST - which
    is the number that makes Bank B's 15.99% the expensive choice.
    """

    offerId: str
    lender: str
    lenderType: Literal["NBFC", "Bank"]
    principal: int
    tenureMonths: int
    ratePa: float
    processingFee: int
    gst: int
    apr: float
    emi: int
    totalRepay: int
    totalCost: int
    badges: list[Literal["lowest_total_cost", "low_rate_high_fee"]]
    kfsUrl: str


class OffersCardData(CardModel):
    suitability: Suitability
    offers: list[OfferSummary]


class OffersCard(CardModel):
    type: Literal["offers"] = "offers"
    data: OffersCardData


# --- KFS ---------------------------------------------------------------------


class KfsLine(CardModel):
    """One of the five lines. `redFlag` is what the app renders in red - the
    charges a customer is most likely to be surprised by later."""

    key: str
    text: str
    redFlag: bool


class KfsCardData(CardModel):
    offerId: str
    lender: str
    version: str
    lines: list[KfsLine]
    pdfUrl: str
    sample: Literal[True] = True


class KfsCard(CardModel):
    type: Literal["kfs"] = "kfs"
    data: KfsCardData


# --- quiz --------------------------------------------------------------------


class QuizOption(CardModel):
    id: str
    text: str


class QuizResult(CardModel):
    correct: bool
    explanation: str | None = None


class QuizCardData(CardModel):
    questionId: str
    index: int
    total: int
    prompt: str
    options: list[QuizOption]
    attempt: int
    maxAttempts: int
    result: QuizResult | None = None


class QuizCard(CardModel):
    type: Literal["quiz"] = "quiz"
    data: QuizCardData


# --- consent lock ------------------------------------------------------------


class InsuranceChoice(CardModel):
    """The optional add-on. `optional` is a literal so no client can render it
    as a requirement, and `granted` defaults to false everywhere (§7.2)."""

    premium: int
    granted: bool = False
    optional: Literal[True] = True


class ConsentLockCardData(CardModel):
    """`acceptEnabled` is decided by the backend from the teach-back result and
    re-checked when the tap arrives, so a patched client gains nothing (§9)."""

    acceptEnabled: bool
    reason: str | None = None
    terms: list[str]
    insurance: InsuranceChoice


class ConsentLockCard(CardModel):
    type: Literal["consent_lock"] = "consent_lock"
    data: ConsentLockCardData


# --- OTP ---------------------------------------------------------------------


class OtpCardData(CardModel):
    """`demoCode` is present only with `OTP_DEMO=true` in dev (§13.6); the app
    shows it as an obvious fake-SMS banner so nobody mistakes it for real."""

    length: Literal[6] = 6
    expiresInSec: int
    attemptsLeft: int
    demoCode: str | None = None


class OtpCard(CardModel):
    type: Literal["otp"] = "otp"
    data: OtpCardData


# --- receipt -----------------------------------------------------------------


class TeachbackScore(CardModel):
    passed: int
    total: int


class ReceiptCardData(CardModel):
    receiptNo: str
    lender: str
    emi: int
    tenureMonths: int
    totalRepay: int
    language: Lang
    teachback: TeachbackScore
    insuranceTaken: bool
    publicUrl: str
    summaryText: str
    createdAt: str


class ReceiptCard(CardModel):
    type: Literal["receipt"] = "receipt"
    data: ReceiptCardData


# --- handoff -----------------------------------------------------------------


class HandoffCardData(CardModel):
    message: str
    window: str


class HandoffCard(CardModel):
    type: Literal["handoff"] = "handoff"
    data: HandoffCardData


# --- the union ---------------------------------------------------------------

Card = Annotated[
    LanguageCard
    | AmountCard
    | ConsentCard
    | ManualFormCard
    | PrefillCard
    | ConfirmCard
    | OffersCard
    | KfsCard
    | QuizCard
    | ConsentLockCard
    | OtpCard
    | ReceiptCard
    | HandoffCard,
    Field(discriminator="type"),
]
