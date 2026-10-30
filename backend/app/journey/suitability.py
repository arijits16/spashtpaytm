"""Is this loan suitable for this customer? (build plan §9 OFFERS)

Three gates, all of them from the plan: the instalment must not exceed half the
verified monthly income, the borrower must be between 21 and 60, and the amount
must not exceed three months' income. A customer who fails is not shown offers
at all - they are handed to a human.

The reasons are written for the **customer**, in their language, not for an
underwriter. "Your EMI would be 62% of your income" is something a person can
act on; "FOIR breach" is not. That is the difference between a refusal and an
explanation, and it is the whole point of the product.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.journey.loan_math import emi as compute_emi
from app.journey.loan_math import foir as compute_foir
from app.journey.states import Lang

# §9: pass if FOIR <= 50%, age 21-60, amount <= 3x monthly income.
MAX_FOIR = 0.50
MIN_AGE, MAX_AGE = 21, 60
MAX_AMOUNT_MULTIPLE = 3

# Reason strings per language. Kept here rather than in the speech templates
# because these are *card* text, not spoken lines, and they are composed from
# figures that are already on screen so the Number Guard has nothing to check.
_REASONS: dict[str, dict[Lang, str]] = {
    "emi_share": {
        "mr-IN": "तुमचा EMI तुमच्या मिळकतीच्या {PCT}% आहे",
        "hi-IN": "आपकी EMI आपकी आय का {PCT}% है",
        "en-IN": "Your EMI is {PCT}% of your verified income",
    },
    "emi_too_high": {
        "mr-IN": "हा EMI तुमच्या मिळकतीच्या {PCT}% होतो, जे खूप जास्त आहे",
        "hi-IN": "यह EMI आपकी आय का {PCT}% बनता है, जो बहुत ज़्यादा है",
        "en-IN": "This EMI would be {PCT}% of your income, which is too high",
    },
    "income_verified": {
        "mr-IN": "६ महिन्यांच्या बँक माहितीवरून तपासलेली मिळकत",
        "hi-IN": "6 महीने की बैंक जानकारी से जाँची गई आय",
        "en-IN": "Income verified from 6 months of bank data",
    },
    "income_declared": {
        "mr-IN": "तुम्ही सांगितलेली मिळकत (बँक माहिती घेतली नाही)",
        "hi-IN": "आपकी बताई हुई आय (बैंक जानकारी नहीं ली)",
        "en-IN": "Income as you declared it (no bank data was shared)",
    },
    "existing_emi": {
        "mr-IN": "आधीचा EMI ₹{EXISTING} धरून",
        "hi-IN": "पहले का EMI ₹{EXISTING} मिलाकर",
        "en-IN": "Including your existing EMI of ₹{EXISTING}",
    },
    "amount_too_high": {
        "mr-IN": "मागितलेली रक्कम तुमच्या {MONTHS} महिन्यांच्या मिळकतीपेक्षा जास्त आहे",
        "hi-IN": "माँगी गई रकम आपकी {MONTHS} महीने की आय से ज़्यादा है",
        "en-IN": "The amount is more than {MONTHS} months of your income",
    },
    "age": {
        "mr-IN": "या कर्जासाठी वय {MIN} ते {MAX} असावं लागतं",
        "hi-IN": "इस लोन के लिए उम्र {MIN} से {MAX} होनी चाहिए",
        "en-IN": "This loan is for ages {MIN} to {MAX}",
    },
    "no_income": {
        "mr-IN": "मिळकतीची माहिती मिळाली नाही",
        "hi-IN": "आय की जानकारी नहीं मिली",
        "en-IN": "We could not establish your income",
    },
}


def _reason(key: str, language: Lang, **values: object) -> str:
    text = _REASONS[key].get(language, _REASONS[key]["en-IN"])
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


@dataclass(frozen=True, slots=True)
class SuitabilityDecision:
    """The verdict, plus the numbers behind it.

    `foir` is the fraction (0.162) and `foir_pct` the percentage (16.2): the
    card shows the percentage and the receipt stores the fraction, and keeping
    both here means neither is recomputed at the point of use.
    """

    suitable: bool
    foir: float
    foir_pct: float
    reasons: list[str]
    reference_emi: int

    @property
    def decision(self) -> str:
        return "suitable" if self.suitable else "not_suitable"


def assess(
    *,
    amount: int,
    tenure_months: int,
    reference_rate_pct: float,
    monthly_income: int | None,
    existing_emi: int,
    age: int | None,
    language: Lang,
    income_verified: bool = True,
) -> SuitabilityDecision:
    """Decide whether to show offers.

    @param reference_rate_pct  The rate used to size the test instalment.
                               The cheapest offer's APR would flatter the
                               customer into an EMI they cannot carry, so the
                               *highest* available rate is passed in: if the
                               worst offer is affordable, every offer is.
    @param income_verified     False when the customer declined data sharing
                               and typed their income, which the reasons say
                               out loud so the receipt is not misleading.

    Every failing gate is reported, not just the first. Someone refused for two
    reasons deserves to hear both rather than fix one and be refused again.
    """
    reasons: list[str] = []

    if not monthly_income or monthly_income <= 0:
        return SuitabilityDecision(
            suitable=False,
            foir=0.0,
            foir_pct=0.0,
            reasons=[_reason("no_income", language)],
            reference_emi=0,
        )

    reference_emi = compute_emi(amount, reference_rate_pct, tenure_months)
    ratio = compute_foir(existing_emi, reference_emi, monthly_income)
    ratio_pct = round(ratio * 100, 1)

    failures: list[str] = []

    if ratio > MAX_FOIR:
        failures.append(_reason("emi_too_high", language, PCT=round(ratio_pct)))

    if age is not None and not (MIN_AGE <= age <= MAX_AGE):
        failures.append(_reason("age", language, MIN=MIN_AGE, MAX=MAX_AGE))

    if amount > MAX_AMOUNT_MULTIPLE * monthly_income:
        failures.append(_reason("amount_too_high", language, MONTHS=MAX_AMOUNT_MULTIPLE))

    if failures:
        reasons = failures
    else:
        reasons.append(_reason("emi_share", language, PCT=round(ratio_pct)))
        reasons.append(
            _reason("income_verified" if income_verified else "income_declared", language)
        )
        if existing_emi > 0:
            reasons.append(_reason("existing_emi", language, EXISTING=f"{existing_emi:,}"))

    return SuitabilityDecision(
        suitable=not failures,
        foir=round(ratio, 4),
        foir_pct=ratio_pct,
        reasons=reasons,
        reference_emi=reference_emi,
    )
