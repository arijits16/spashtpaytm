"""The extraction schema, and what the extracted fields mean (build plan §8.5, phase 11).

Sarvam Document Intelligence takes an **inline JSON schema** whose every field
carries a `type` and a `description`, and returns a `result` object plus
`annotations` holding per-field confidence and the source span it read from.

The descriptions are the whole interface. A field called `late_fee` with the
description "late payment charge per instalment, in rupees" extracts correctly
from a document the model has never seen; one called `late_fee` with no
description extracts the foreclosure charge about a third of the time. They are
written the way an RBI-format KFS words its own rows.

**Nothing here decides anything.** Extraction produces candidate numbers with
confidence scores; a human then verifies them, and only after that do they
become facts a customer is quoted (§11, "human verification is required").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

FieldKind = Literal["money", "percent", "count", "text"]


@dataclass(frozen=True, slots=True)
class Field:
    """One extractable field, and how to read it back.

    @param key          The `facts` key it becomes once verified.
    @param kind         How the value is parsed and displayed.
    @param description  Sent to the model. Written in the KFS's own language.
    @param labels       Row labels the offline `pdfplumber` fallback matches on.
    @param required     A document missing this cannot be published.
    """

    key: str
    kind: FieldKind
    description: str
    labels: tuple[str, ...]
    required: bool = True


# The RBI's prescribed order, which is also the order the sample PDFs print in.
FIELDS: tuple[Field, ...] = (
    Field(
        "principal",
        "money",
        "The loan amount sanctioned to the borrower, in rupees. Digits only.",
        ("Loan amount sanctioned", "Loan amount", "Sanctioned amount"),
    ),
    Field(
        "processing_fee",
        "money",
        "The one-time processing fee charged by the lender, in rupees, excluding GST.",
        ("Processing fee",),
    ),
    Field(
        "gst",
        "money",
        "The GST charged on the processing fee, in rupees.",
        ("GST on processing fee", "GST"),
    ),
    Field(
        "net_disbursed",
        "money",
        "The net amount actually credited to the borrower after fees, in rupees.",
        ("Net amount credited to borrower", "Net amount credited", "Net disbursed"),
    ),
    Field(
        "tenure_months",
        "count",
        "The loan tenure in months. A number of months, not years.",
        ("Tenure", "Number of instalments"),
    ),
    Field(
        "rate_pa",
        "percent",
        "The annual rate of interest as a percentage, on a reducing balance.",
        ("Rate of interest (per annum)", "Rate of interest"),
    ),
    Field(
        "apr",
        "percent",
        "The all-inclusive Annual Percentage Rate as a percentage.",
        ("Annual Percentage Rate (APR), all-inclusive", "Annual Percentage Rate", "APR"),
    ),
    Field(
        "emi",
        "money",
        "The monthly instalment (EMI) the borrower pays, in rupees.",
        ("Monthly instalment (EMI)", "Monthly instalment", "EMI"),
    ),
    Field(
        "total_interest",
        "money",
        "The total interest payable over the whole tenure, in rupees.",
        ("Total interest payable", "Total interest"),
    ),
    Field(
        "total_repay",
        "money",
        "The total amount repayable over the whole tenure, in rupees.",
        ("Total amount repayable", "Total repayable"),
    ),
    Field(
        "total_cost",
        "money",
        "The total cost of credit to the borrower, in rupees: interest plus all fees.",
        ("Total cost of credit to borrower", "Total cost of credit"),
    ),
    Field(
        "late_fee",
        "money",
        "The late payment charge per missed or delayed instalment, in rupees.",
        ("Late payment charge, per instalment", "Late payment charge", "Late fee"),
    ),
    Field(
        "foreclosure_pct",
        "percent",
        "The foreclosure or prepayment charge, as a percentage of the principal outstanding.",
        ("Foreclosure charge", "Prepayment charge"),
    ),
    Field(
        "cooling_off_days",
        "count",
        "The cooling-off or look-up period, in days, during which the borrower may exit.",
        ("Cooling-off / look-up period", "Cooling-off period", "Look-up period"),
    ),
    Field(
        "insurance_premium",
        "money",
        "The one-time credit-life insurance premium, in rupees. Zero if there is none.",
        ("Credit-life insurance", "Insurance premium"),
        required=False,
    ),
)

FIELDS_BY_KEY: dict[str, Field] = {field.key: field for field in FIELDS}

REQUIRED_KEYS: tuple[str, ...] = tuple(field.key for field in FIELDS if field.required)

# Below this, a field is shown amber on the dashboard and the publish button
# stays disabled until a human has looked at it. 0.75 rather than 0.9: the
# point of the threshold is to direct attention, and a threshold nothing ever
# trips is one nobody reads.
LOW_CONFIDENCE = 0.75


def json_schema() -> dict[str, Any]:
    """The inline JSON schema sent to `POST /doc-ai/v1/job/extract`.

    Every value is typed `string`: a KFS writes "INR 4,600" and "18.67%
    (reducing balance)", and asking the model for a number means asking it to
    parse as well as read. We parse, in `parse_value`, where the rules are
    testable and a surprise is a failed parse rather than a silently wrong
    figure.
    """
    return {
        "type": "object",
        "properties": {
            field.key: {"type": "string", "description": field.description} for field in FIELDS
        },
        "required": list(REQUIRED_KEYS),
    }
