"""The Number Guard (build plan §10.5).

**The product's single most important safety control.** Spasht is a system that
reads loan terms aloud to someone who cannot easily read them. If a language
model ever says an EMI of ₹4,000 when the real one is ₹4,600, the whole product
becomes worse than the thing it replaces - because the customer now has a number
they trust and it is wrong.

So no generated text reaches a customer without passing through here. The rule
is absolute and the direction of failure is deliberate: **any number not in the
allow-list rejects the whole text**, and the seeded template is used instead. A
slightly stiff sentence that is true beats a fluent one that is not.

**What is allowed** (§10.5):

* every numeric fact of the offers on screen - at OFFERS that is all three, and
  after selection only the chosen one;
* the customer's own figures on screen: the requested amount, their verified
  income, the EMI-to-income percentage;
* the small counts {1, 2, 3}, because "3 questions" and "question 2" are
  unavoidable and carry no financial meaning.

**Normalisation before comparison**: Devanagari digits to ASCII, separators
stripped, हजार / लाख / thousand / lakh expanded. "४,६००" and "4600" and
"4.6 हजार" are the same number, and a guard that could be defeated by writing a
figure in the other script would be decoration.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

_DIGIT_MAP = str.maketrans("०१२३४५६७८९", "0123456789")

# Counts the assistant must be able to say. Deliberately tiny: these are
# question numbers and attempt counts, never money.
SAFE_SMALL_NUMBERS: frozenset[float] = frozenset({1.0, 2.0, 3.0})

# Multipliers, so "4.6 हजार" is compared as 4600.
_MULTIPLIERS: tuple[tuple[str, float], ...] = (
    ("लाख", 100_000.0),
    ("lakh", 100_000.0),
    ("lac", 100_000.0),
    ("हजार", 1_000.0),
    ("हज़ार", 1_000.0),
    ("hazaar", 1_000.0),
    ("thousand", 1_000.0),
)

# Any run of digits, with optional grouping and decimals.
_NUMBER_RE = re.compile(r"\d+(?:[,\s]\d{2,3})*(?:\.\d+)?")

# Percentages are compared to two decimals; money to the rupee. A tolerance,
# not equality, because "18.67%" and "18.7%" differ only by rounding and both
# describe the same approved fact.
_TOLERANCE = 0.011

# The numeric fact keys of an offer (`PricedOffer.facts`) that may be spoken.
_OFFER_FACT_KEYS = (
    "principal",
    "tenure_months",
    "rate_pa",
    "processing_fee",
    "gst",
    "net_disbursed",
    "emi",
    "total_repay",
    "total_interest",
    "total_cost",
    "apr",
    "late_fee",
    "foreclosure_pct",
    "cooling_off_days",
    "insurance_premium",
)


@dataclass
class GuardVerdict:
    """Whether a generated text may be shown.

    `blocked_numbers` is what gets audited and counted on the dashboard (§12):
    "AI numbers blocked by the guard" is a KPI, because a guard that never
    fires is either unnecessary or broken, and the operator should be able to
    tell which.
    """

    allowed: bool
    blocked_numbers: list[float] = field(default_factory=list)
    found_numbers: list[float] = field(default_factory=list)

    @property
    def reason(self) -> str | None:
        if self.allowed:
            return None
        rendered = ", ".join(_render(value) for value in self.blocked_numbers)
        return f"text contains number(s) not in the facts: {rendered}"


def _render(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:g}"


def normalise(text: str) -> str:
    """Fold text so numbers compare across scripts and separators."""
    folded = unicodedata.normalize("NFKC", text).translate(_DIGIT_MAP)
    # Strip separators *inside* a number only, so "4,600" becomes "4600" while
    # a comma between two sentences is left alone.
    return re.sub(r"(?<=\d)[,\s](?=\d{2,3}\b)", "", folded)


# Markers that make a number a sum of money. A figure wearing one of these is
# never covered by the safe-small-count allowance - see `extract_numbers`.
_MONEY_BEFORE = ("₹", "rs", "inr")
_MONEY_AFTER = ("रुपये", "रुपए", "rupees", "rupee", "%", "टक्के", "प्रतिशत", "percent")


def extract_numbers(text: str) -> list[tuple[float, bool]]:
    """Every number in `text`, as `(value, is_money)`.

    A figure followed by a multiplier word counts as the product, so
    "4.6 हजार" is 4600 and cannot slip past a guard that only saw "4.6".

    `is_money` is what stops the small-count allowance being abused. {1, 2, 3}
    are permitted so the assistant can say "3 questions" - but "EMI ₹1" would
    then also pass, which is exactly the kind of invented figure this guard
    exists to block. A number wearing a currency symbol or a percent sign has
    to be a real fact, whatever its size.
    """
    normalised = normalise(text)
    found: list[tuple[float, bool]] = []

    for match in _NUMBER_RE.finditer(normalised):
        raw = match.group(0).replace(",", "").replace(" ", "")
        try:
            value = float(raw)
        except ValueError:
            continue

        tail = normalised[match.end() : match.end() + 14].lower().strip()
        for word, factor in _MULTIPLIERS:
            if tail.startswith(word):
                value *= factor
                break

        head = normalised[max(0, match.start() - 4) : match.start()].lower()
        is_money = any(marker in head for marker in _MONEY_BEFORE) or any(
            tail.startswith(marker) for marker in _MONEY_AFTER
        )

        found.append((value, is_money))

    return found


def allowed_values(
    *,
    offers: list[dict[str, Any]] | None = None,
    customer: dict[str, Any] | None = None,
    extra: list[float] | None = None,
) -> set[float]:
    """Build the allow-list for one turn.

    @param offers    `PricedOffer.facts` for every offer **on screen**. All
                     three at OFFERS; only the selected one afterwards, because
                     after selection the other two are no longer facts about
                     this customer's loan.
    @param customer  The figures shown about the customer: `amount`,
                     `monthly_income`, `foir_pct`.
    """
    values: set[float] = set(SAFE_SMALL_NUMBERS)

    for facts in offers or []:
        for key in _OFFER_FACT_KEYS:
            value = facts.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.add(float(value))

    for key in ("amount", "monthly_income", "existing_emi", "foir_pct"):
        value = (customer or {}).get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.add(float(value))

    values.update(float(value) for value in extra or [])

    # A rate like 18.67 is also legitimately said as "18.67 percent" and
    # sometimes rounded to "19" in speech. Rounding is NOT allowed: an EMI
    # rounded to "4,000" is exactly the failure this guard exists to prevent,
    # and there is no way to permit rounding for rates without permitting it
    # for money. The templates say the exact figure, so nothing needs it.
    return values


def check(
    text: str,
    *,
    offers: list[dict[str, Any]] | None = None,
    customer: dict[str, Any] | None = None,
    extra: list[float] | None = None,
) -> GuardVerdict:
    """Decide whether generated `text` may be shown."""
    facts = allowed_values(offers=offers, customer=customer, extra=extra)
    # A money figure has to match a real fact. A bare count may additionally be
    # 1, 2 or 3, so the assistant can say "3 questions" without "EMI ₹1" also
    # becoming sayable.
    money_only = facts - SAFE_SMALL_NUMBERS
    found = extract_numbers(text)

    blocked = [
        value
        for value, is_money in found
        if not any(
            abs(value - permitted) <= _TOLERANCE
            for permitted in (money_only if is_money else facts)
        )
    ]

    return GuardVerdict(
        allowed=not blocked,
        blocked_numbers=blocked,
        found_numbers=[value for value, _ in found],
    )


def guard(
    text: str,
    fallback: str,
    *,
    offers: list[dict[str, Any]] | None = None,
    customer: dict[str, Any] | None = None,
    extra: list[float] | None = None,
    on_block: Any = None,
) -> tuple[str, GuardVerdict]:
    """Return `text` if it passes, otherwise `fallback`.

    The single function every generation path calls. Returning the fallback
    rather than raising is what keeps the journey moving: a blocked
    re-explanation becomes the seeded one, and the customer gets a correct
    sentence instead of an error.

    @param on_block  Called with the verdict when the text is rejected, so the
                     caller can write the `guard.blocked` audit event without
                     this module needing a database session.
    """
    verdict = check(text, offers=offers, customer=customer, extra=extra)
    if verdict.allowed:
        return text, verdict

    log.warning(
        "number guard blocked generated text",
        extra={
            "blocked": verdict.blocked_numbers,
            # The text itself is not logged: it may quote the customer.
            "chars": len(text),
        },
    )
    if on_block is not None:
        on_block(verdict)

    return fallback, verdict
