"""Turning what a KFS says into numbers (build plan phase 11).

A Key Fact Statement is written for a person, so its figures arrive as
"INR 4,600", "18.67% (reducing balance)", "12 months", "4% of principal
outstanding". The extraction engines return those strings verbatim - both of
them, deliberately, so that the model is never asked to parse as well as read.

This module is the one place that parses. It is strict in a specific way: a
value it cannot read becomes `None` rather than a guess, and `None` reaches the
dashboard as "could not read" for a human to fill in. A loan figure guessed from
an unreadable PDF is the exact failure the Number Guard exists to prevent, and
it would arrive here with a confidence score attached, looking trustworthy.
"""

from __future__ import annotations

import logging
import re

from app.kfs.schema import FIELDS_BY_KEY, FieldKind

log = logging.getLogger(__name__)

# "INR 1,00,000" / "₹ 4,600" / "4600.00" - the first number in the string, with
# Indian or Western digit grouping, optionally fractional.
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")

# A KFS says "OPTIONAL · one-time INR 750" for insurance, where the figure is
# not the first number on the line in every lender's wording. Anchoring on the
# currency marker finds it when one is present.
_CURRENCY_NUMBER = re.compile(r"(?:INR|₹|Rs\.?)\s*(-?\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)


def parse_value(raw: object, kind: FieldKind) -> float | int | None:
    """Parse one extracted value, or None if it cannot be read.

    `money` and `count` come back as `int` because every KFS figure in rupees or
    months is whole; `percent` stays a `float` because 18.67% is not 19%, and
    rounding a rate is how an APR comparison stops being true.
    """
    if raw is None:
        return None

    if isinstance(raw, bool):
        return None

    if isinstance(raw, (int, float)):
        number = float(raw)
    else:
        text = str(raw).strip()
        if not text:
            return None

        # "no charge", "nil", "not applicable" are real KFS wordings for zero.
        if re.fullmatch(r"(nil|none|no charge|not applicable|n/?a|free)\.?", text, re.IGNORECASE):
            return 0 if kind in ("money", "count") else 0.0

        match = _CURRENCY_NUMBER.search(text) if kind == "money" else None
        if match is None:
            match = _NUMBER.search(text)
        if match is None:
            return None

        group = match.group(1) if match.re is _CURRENCY_NUMBER else match.group(0)
        try:
            number = float(group.replace(",", ""))
        except ValueError:
            return None

    if kind in ("money", "count"):
        return round(number)
    return round(number, 2)


def parse_fields(raw: dict[str, object]) -> dict[str, float | int | None]:
    """Parse every known field of an extraction result.

    Unknown keys are dropped rather than carried through: the schema is the
    contract, and a model that invented a field has not read a KFS row.
    """
    parsed: dict[str, float | int | None] = {}
    for key, value in raw.items():
        field = FIELDS_BY_KEY.get(key)
        if field is None:
            log.info("extraction returned an unknown field", extra={"field": key})
            continue
        parsed[key] = parse_value(value, field.kind)
    return parsed


def sanity_problems(facts: dict[str, float | int | None]) -> list[str]:
    """Internal inconsistencies worth showing a human before they verify.

    Not a rejection: the document says what it says, and a KFS whose own
    arithmetic does not add up is itself a finding. These are the lines the
    dashboard puts next to the Verify button, because an extraction can be
    confident and wrong in ways a human eye catches instantly.
    """
    problems: list[str] = []

    def number(key: str) -> float | None:
        value = facts.get(key)
        return float(value) if isinstance(value, (int, float)) else None

    principal, emi = number("principal"), number("emi")
    tenure, total_repay = number("tenure_months"), number("total_repay")
    total_interest, total_cost = number("total_interest"), number("total_cost")
    fee, gst, net = number("processing_fee"), number("gst"), number("net_disbursed")
    rate, apr = number("rate_pa"), number("apr")

    if (
        emi
        and tenure
        and total_repay
        and abs(emi * tenure - total_repay) > max(50.0, total_repay * 0.02)
    ):
        problems.append("EMI x tenure does not match the total repayable")

    if (
        principal
        and total_repay
        and total_interest
        and abs((principal + total_interest) - total_repay) > 50
    ):
        problems.append("principal + total interest does not match the total repayable")

    if (
        principal
        and net is not None
        and fee is not None
        and gst is not None
        and abs((principal - fee - gst) - net) > 50
    ):
        problems.append("principal - fees does not match the net amount credited")

    if (
        total_cost is not None
        and total_interest is not None
        and fee is not None
        and total_cost + 50 < total_interest + fee
    ):
        problems.append("the total cost of credit is lower than interest plus fees")

    if rate and apr and apr + 0.01 < rate:
        problems.append("the APR is below the interest rate, which fees cannot produce")

    if tenure and not 1 <= tenure <= 360:
        problems.append("the tenure is outside 1-360 months")

    return problems
